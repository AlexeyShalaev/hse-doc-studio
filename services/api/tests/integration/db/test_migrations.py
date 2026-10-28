from __future__ import annotations

import asyncio

import pytest
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.errors import DbOutdatedError, MigrationLockTimeoutError
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.pg


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))


def test__migrations__chain__has_single_head() -> None:
    assert len(migrator.head_revisions()) == 1


async def test__upgrade_head_then_downgrade_base__roundtrips(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine)

    assert await migrator.current_revision(pg_engine) == migrator.head_revision()
    assert "instance_meta" in await _tables(pg_engine)

    await migrator.downgrade(pg_engine, "base")

    assert await migrator.current_revision(pg_engine) is None
    assert "instance_meta" not in await _tables(pg_engine)


async def test__check_drift__after_upgrade__is_empty(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine)

    assert await migrator.check_drift(pg_engine) == []


async def test__check_drift__manual_change__is_reported(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine)
    async with pg_engine.begin() as conn:
        await conn.execute(text("ALTER TABLE instance_meta ADD COLUMN extra text"))

    assert await migrator.check_drift(pg_engine) != []


async def test__migrate_if_needed__second_call__does_nothing(pg_engine: AsyncEngine) -> None:
    assert await migrator.migrate_if_needed(pg_engine) is True
    assert await migrator.migrate_if_needed(pg_engine) is False


async def test__migrate_if_needed__concurrent__applies_once(pg_engine: AsyncEngine) -> None:
    other = create_async_engine(pg_engine.url)
    try:
        results = await asyncio.gather(migrator.migrate_if_needed(pg_engine), migrator.migrate_if_needed(other))
    finally:
        await other.dispose()

    assert sorted(results) == [False, True]
    assert await migrator.current_revision(pg_engine) == migrator.head_revision()


async def test__ensure_db_current__outdated_without_auto__raises(pg_engine: AsyncEngine) -> None:
    with pytest.raises(DbOutdatedError) as exc:
        await migrator.ensure_db_current(pg_engine, auto_migrate=False)

    assert exc.value.code == "db_outdated"


async def test__ensure_db_current__auto_migrate__brings_to_head(pg_engine: AsyncEngine) -> None:
    await migrator.ensure_db_current(pg_engine, auto_migrate=True)
    await migrator.ensure_db_current(pg_engine, auto_migrate=False)

    assert await migrator.current_revision(pg_engine) == migrator.head_revision()


async def test__migrate_if_needed__lock_held_elsewhere__times_out_instead_of_hanging(pg_engine: AsyncEngine) -> None:
    async with pg_engine.connect() as holder:
        await holder.execute(text("SELECT pg_advisory_lock(:key)"), {"key": migrator.MIGRATION_LOCK_KEY})
        try:
            with pytest.raises(MigrationLockTimeoutError):
                await migrator.migrate_if_needed(pg_engine, lock_wait_s=0.3)
        finally:
            await holder.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": migrator.MIGRATION_LOCK_KEY})


async def test__upgrade__works_under_tight_statement_timeout(pg_engine: AsyncEngine) -> None:
    tight = create_async_engine(pg_engine.url, connect_args={"server_settings": {"statement_timeout": "1"}})
    try:
        await migrator.upgrade(tight)
    finally:
        await tight.dispose()

    assert await migrator.current_revision(pg_engine) == migrator.head_revision()
