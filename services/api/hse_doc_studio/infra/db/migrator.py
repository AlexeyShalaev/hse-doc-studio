"""Применение миграций: upgrade, текущая ревизия, дрейф, самомиграция под advisory-локом и охранник."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import structlog
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from hse_doc_studio.infra.db import orm as _orm  # noqa: F401 — регистрирует таблицы в Base.metadata для db check
from hse_doc_studio.infra.db.base import Base
from hse_doc_studio.infra.db.errors import DbAheadError, DbOutdatedError, MigrationLockTimeoutError

logger = structlog.get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
FILE_TEMPLATE = "%%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s"
# Один ключ на всю установку: две реплики или два процесса не мигрируют одновременно.
MIGRATION_LOCK_KEY = 0x48534D31  # "HSM1"
MIGRATION_LOCK_WAIT_S = 600.0
_LOCK_POLL_S = 0.5


def _config(connection: Connection | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("file_template", FILE_TEMPLATE)
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


def head_revisions() -> list[str]:
    return list(ScriptDirectory.from_config(_config()).get_heads())


def head_revision() -> str:
    heads = head_revisions()
    if len(heads) != 1:
        raise RuntimeError(f"в цепочке миграций {len(heads)} head вместо одного: {', '.join(heads)}")
    return heads[0]


def _raise_if_ahead(current: str | None, head: str) -> None:
    """Ревизия, которой нет в цепочке этого образа, значит базу мигрировал более новый код: апгрейдить нечего."""
    if current is None:
        return
    known = {script.revision for script in ScriptDirectory.from_config(_config()).walk_revisions()}
    if current not in known:
        raise DbAheadError(current, head)


def _current(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _drift(connection: Connection) -> list[object]:
    ctx = MigrationContext.configure(connection, opts={"compare_type": True, "compare_server_default": True})
    return list(compare_metadata(ctx, Base.metadata))


async def current_revision(engine: AsyncEngine) -> str | None:
    async with engine.connect() as connection:
        return await connection.run_sync(_current)


async def _without_timeouts(connection: AsyncConnection) -> None:
    # Рабочие statement_timeout и lock_timeout рассчитаны на запросы; миграции могут идти дольше.
    await connection.execute(text("SET LOCAL statement_timeout = 0"))
    await connection.execute(text("SET LOCAL lock_timeout = 0"))


async def upgrade(engine: AsyncEngine, revision: str = "head") -> None:
    async with engine.begin() as connection:
        await _without_timeouts(connection)
        await connection.run_sync(lambda sync: command.upgrade(_config(sync), revision))


async def downgrade(engine: AsyncEngine, revision: str) -> None:
    async with engine.begin() as connection:
        await _without_timeouts(connection)
        await connection.run_sync(lambda sync: command.downgrade(_config(sync), revision))


async def check_drift(engine: AsyncEngine) -> list[object]:
    """Различия между моделями и реальной схемой; пусто, если дрейфа нет."""
    async with engine.connect() as connection:
        return await connection.run_sync(_drift)


async def _acquire_migration_lock(lock_conn: AsyncConnection, wait_s: float) -> None:
    """Опрашиваем pg_try_advisory_lock вместо блокирующего pg_advisory_lock: ожидание ограничено по времени."""
    deadline = time.monotonic() + wait_s
    while True:
        got = (
            await lock_conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        ).scalar_one()
        if got:
            return
        if time.monotonic() >= deadline:
            raise MigrationLockTimeoutError(f"advisory-лок миграций занят другим процессом дольше {wait_s:g} с")
        await asyncio.sleep(_LOCK_POLL_S)


async def migrate_if_needed(engine: AsyncEngine, *, lock_wait_s: float = MIGRATION_LOCK_WAIT_S) -> bool:
    """Довести схему до head под advisory-локом. True, если миграции применялись.

    Лок держит отдельное соединение: пока оно открыто, второй процесс ждёт (не дольше ``lock_wait_s``) и,
    получив лок, видит уже актуальную ревизию и ничего не делает.
    """
    head = head_revision()
    async with engine.connect() as lock_conn:
        await _acquire_migration_lock(lock_conn, lock_wait_s)
        try:
            current = await current_revision(engine)
            if current == head:
                return False
            _raise_if_ahead(current, head)
            await upgrade(engine)
            logger.info("db_migrated", head=head)
            return True
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
            await lock_conn.commit()


async def ensure_db_current(
    engine: AsyncEngine, *, auto_migrate: bool, lock_wait_s: float = MIGRATION_LOCK_WAIT_S
) -> None:
    """Охранник старта: либо мигрирует сам, либо отказывает, если база не на head (``db_outdated``)."""
    if auto_migrate:
        await migrate_if_needed(engine, lock_wait_s=lock_wait_s)
        return
    head = head_revision()
    current = await current_revision(engine)
    if current != head:
        _raise_if_ahead(current, head)
        raise DbOutdatedError(current, head)
