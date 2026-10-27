"""Применение миграций: upgrade, текущая ревизия, дрейф, самомиграция под advisory-локом и охранник."""

from __future__ import annotations

from pathlib import Path

import structlog
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from hse_doc_studio.infra.db.base import Base
from hse_doc_studio.infra.db.errors import DbOutdatedError

logger = structlog.get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
FILE_TEMPLATE = "%%(year)d_%%(month).2d_%%(day).2d_%%(hour).2d%%(minute).2d-%%(rev)s_%%(slug)s"
# Один ключ на всю установку: две реплики или два процесса не мигрируют одновременно.
MIGRATION_LOCK_KEY = 0x48534D31  # "HSM1"


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


def _current(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def _drift(connection: Connection) -> list[object]:
    ctx = MigrationContext.configure(connection, opts={"compare_type": True, "compare_server_default": True})
    return list(compare_metadata(ctx, Base.metadata))


async def current_revision(engine: AsyncEngine) -> str | None:
    async with engine.connect() as connection:
        return await connection.run_sync(_current)


async def upgrade(engine: AsyncEngine, revision: str = "head") -> None:
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: command.upgrade(_config(sync), revision))


async def downgrade(engine: AsyncEngine, revision: str) -> None:
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: command.downgrade(_config(sync), revision))


async def check_drift(engine: AsyncEngine) -> list[object]:
    """Различия между моделями и реальной схемой; пусто, если дрейфа нет."""
    async with engine.connect() as connection:
        return await connection.run_sync(_drift)


async def migrate_if_needed(engine: AsyncEngine) -> bool:
    """Довести схему до head под advisory-локом. True, если миграции применялись.

    Лок держит отдельное соединение: пока оно открыто, второй процесс ждёт и, получив лок,
    видит уже актуальную ревизию и ничего не делает.
    """
    head = head_revision()
    async with engine.connect() as lock_conn:
        await lock_conn.execute(text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK_KEY})
        try:
            if await current_revision(engine) == head:
                return False
            await upgrade(engine)
            logger.info("db_migrated", head=head)
            return True
        finally:
            await lock_conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK_KEY})
            await lock_conn.commit()


async def ensure_db_current(engine: AsyncEngine, *, auto_migrate: bool) -> None:
    """Охранник старта: либо мигрирует сам, либо отказывает, если база не на head (``db_outdated``)."""
    if auto_migrate:
        await migrate_if_needed(engine)
        return
    head = head_revision()
    current = await current_revision(engine)
    if current != head:
        raise DbOutdatedError(current, head)
