from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from hse_doc_studio.infra.db.engine import async_dsn
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.pg

_ENV = "HSE_TEST_PG_DSN"


@pytest.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    """Пустая база на каждый тест; без HSE_TEST_PG_DSN тест пропускается."""
    dsn = os.environ.get(_ENV)
    if not dsn:
        pytest.skip(f"{_ENV} не задан")
    admin = create_async_engine(async_dsn(dsn), isolation_level="AUTOCOMMIT")
    name = f"hse_t_{uuid.uuid4().hex[:12]}"
    async with admin.connect() as conn:
        await conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(async_dsn(dsn)).set(database=name)
    engine = create_async_engine(url)
    try:
        yield engine
    finally:
        await engine.dispose()
        async with admin.connect() as conn:
            await conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        await admin.dispose()
