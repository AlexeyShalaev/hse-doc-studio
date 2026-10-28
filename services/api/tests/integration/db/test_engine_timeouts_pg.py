"""Таймауты движка: настройки доходят до Postgres, зависшее соединение не держит запрос бесконечно."""

from __future__ import annotations

import pytest
from hse_doc_studio.api.config.db import DbConfig
from hse_doc_studio.infra.db.engine import create_engine
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.pg


def _cfg(pg_engine, **kwargs) -> DbConfig:  # type: ignore[no-untyped-def]
    return DbConfig(dsn=pg_engine.url.render_as_string(hide_password=False), **kwargs)


async def test__engine__server_settings_and_pool_timeout_applied(pg_engine) -> None:
    engine = create_engine(_cfg(pg_engine, statement_timeout_s=7, lock_timeout_s=3, pool_timeout_s=4))
    try:
        async with engine.connect() as conn:
            statement = (await conn.execute(text("SHOW statement_timeout"))).scalar_one()
            lock = (await conn.execute(text("SHOW lock_timeout"))).scalar_one()
        assert (statement, lock) == ("7s", "3s")
        assert engine.pool.timeout() == 4  # type: ignore[attr-defined]
    finally:
        await engine.dispose()


async def test__engine__slow_statement__cancelled_by_statement_timeout(pg_engine) -> None:
    engine = create_engine(_cfg(pg_engine, statement_timeout_s=0.2, command_timeout_s=5))
    try:
        async with engine.connect() as conn:
            with pytest.raises(DBAPIError):
                await conn.execute(text("SELECT pg_sleep(3)"))
    finally:
        await engine.dispose()
