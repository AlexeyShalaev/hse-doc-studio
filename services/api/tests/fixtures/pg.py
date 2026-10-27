"""Postgres для тестов с маркером pg.

`HSE_TEST_PG_DSN` указывает на сервер (суперпользователь или владелец с CREATE DATABASE). Без него
тесты пропускаются. Схема с миграциями применяется один раз на прогон в шаблонную базу, каждый
тест получает копию через `CREATE DATABASE ... TEMPLATE`, это на порядок быстрее, чем гонять alembic.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from sqlalchemy.engine import URL
    from sqlalchemy.ext.asyncio import AsyncEngine

PG_DSN_ENV = "HSE_TEST_PG_DSN"

PgDbFactory = Callable[[], Awaitable["AsyncEngine"]]


def _server_url() -> URL:
    from hse_doc_studio.infra.db.engine import async_dsn
    from sqlalchemy.engine import make_url

    dsn = os.environ.get(PG_DSN_ENV)
    if not dsn:
        pytest.skip(f"{PG_DSN_ENV} не задан")
    return make_url(async_dsn(dsn))


def _admin_engine(url: URL) -> AsyncEngine:
    from sqlalchemy.ext.asyncio import create_async_engine

    return create_async_engine(url, isolation_level="AUTOCOMMIT")


async def _create_db(admin: AsyncEngine, name: str, template: str | None = None) -> None:
    from sqlalchemy import text

    suffix = f' TEMPLATE "{template}"' if template else ""
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"{suffix}'))


async def _drop_db(admin: AsyncEngine, name: str) -> None:
    from sqlalchemy import text

    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


@pytest.fixture(scope="session")
def pg_server_url() -> URL:
    return _server_url()


@pytest_asyncio.fixture(scope="session")
async def pg_template_name(pg_server_url: URL) -> AsyncIterator[str]:
    """Имя шаблонной базы с миграциями до head; ревизия входит в имя, чужие прогоны не мешают."""
    from hse_doc_studio.infra.db import migrator
    from sqlalchemy.ext.asyncio import create_async_engine

    head = hashlib.sha1(migrator.head_revision().encode(), usedforsecurity=False).hexdigest()[:8]
    name = f"hse_tpl_{head}_{uuid.uuid4().hex[:8]}"
    admin = _admin_engine(pg_server_url)
    await _create_db(admin, name)
    engine = create_async_engine(pg_server_url.set(database=name))
    try:
        await migrator.upgrade(engine)
    finally:
        await engine.dispose()
    try:
        yield name
    finally:
        await _drop_db(admin, name)
        await admin.dispose()


@pytest_asyncio.fixture
async def pg_db_factory(pg_server_url: URL, pg_template_name: str) -> AsyncIterator[PgDbFactory]:
    """Фабрика баз из шаблона: каждый вызов даёт новую изолированную базу, в конце всё удаляется."""
    from sqlalchemy.ext.asyncio import create_async_engine

    admin = _admin_engine(pg_server_url)
    created: list[tuple[str, AsyncEngine]] = []

    async def make() -> AsyncEngine:
        name = f"hse_t_{uuid.uuid4().hex[:12]}"
        await _create_db(admin, name, template=pg_template_name)
        engine = create_async_engine(pg_server_url.set(database=name))
        created.append((name, engine))
        return engine

    try:
        yield make
    finally:
        for name, engine in created:
            await engine.dispose()
            await _drop_db(admin, name)
        await admin.dispose()


@pytest_asyncio.fixture
async def pg_migrated_engine(pg_db_factory: PgDbFactory) -> AsyncEngine:
    """База с миграциями до head, своя на тест."""
    return await pg_db_factory()


@pytest_asyncio.fixture
async def pg_engine(pg_server_url: URL) -> AsyncIterator[AsyncEngine]:
    """Пустая база без схемы: для тестов самих миграций."""
    from sqlalchemy.ext.asyncio import create_async_engine

    admin = _admin_engine(pg_server_url)
    name = f"hse_t_{uuid.uuid4().hex[:12]}"
    await _create_db(admin, name)
    engine = create_async_engine(pg_server_url.set(database=name))
    try:
        yield engine
    finally:
        await engine.dispose()
        await _drop_db(admin, name)
        await admin.dispose()
