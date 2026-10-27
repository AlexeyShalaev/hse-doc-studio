from __future__ import annotations

import pytest
from hse_doc_studio.infra.db import migrator
from sqlalchemy import text

from tests.fixtures.pg import PgDbFactory

pytestmark = pytest.mark.pg

_INSERT = text("INSERT INTO instance_meta (key, value) VALUES ('k', 'v')")
_COUNT = text("SELECT count(*) FROM instance_meta")


async def test__pg_migrated_engine__is_at_head(pg_migrated_engine) -> None:
    assert await migrator.current_revision(pg_migrated_engine) == migrator.head_revision()


async def test__pg_db_factory__two_databases__are_isolated(pg_db_factory: PgDbFactory) -> None:
    first = await pg_db_factory()
    second = await pg_db_factory()

    async with first.begin() as conn:
        await conn.execute(_INSERT)

    async with first.connect() as conn:
        assert (await conn.execute(_COUNT)).scalar_one() == 1
    async with second.connect() as conn:
        assert (await conn.execute(_COUNT)).scalar_one() == 0


async def test__server_settings__points_to_test_database(server_settings, pg_migrated_engine) -> None:
    assert server_settings.mode.value == "server"
    assert server_settings.db.dsn is not None
    assert pg_migrated_engine.url.database in server_settings.db.dsn
