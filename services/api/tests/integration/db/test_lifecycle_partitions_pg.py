"""Партиционирование журналов против Postgres: маршрутизация строк, автосоздание и отбрасывание партиций, откат."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.lifecycle.ports import PurgeContext
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.lifecycle.sql_sources import PartitionedTableSource
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

_BATCH_AUDIT = "SELECT audit_log_purge_batch(:cutoff, :n)"
_BATCH_AI = "DELETE FROM ai_usage WHERE id IN (SELECT id FROM ai_usage WHERE at < :cutoff ORDER BY at LIMIT :n)"


def _audit(engine: AsyncEngine, *, months_ahead: int = 2) -> PartitionedTableSource:
    return PartitionedTableSource(
        SessionProvider(create_sessionmaker(engine)),
        "audit_log",
        "audit_log",
        months_ahead=months_ahead,
        pause_s=0,
        batch_delete=_BATCH_AUDIT,
        batch_returns_count=True,
    )


def _ai(engine: AsyncEngine) -> PartitionedTableSource:
    return PartitionedTableSource(
        SessionProvider(create_sessionmaker(engine)),
        "ai_usage",
        "ai_usage",
        months_ahead=2,
        pause_s=0,
        batch_delete=_BATCH_AI,
    )


def _ctx(cutoff: datetime | None, batch: int = 1000) -> PurgeContext:
    return PurgeContext(now=datetime.now(UTC), cutoff=cutoff, batch_size=batch, deadline=time.monotonic() + 60)


async def _names(engine: AsyncEngine, parent: str) -> list[str]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT part_name FROM lifecycle_partition_bounds(:t) ORDER BY upper_bound NULLS LAST"), {"t": parent}
        )
        return [r[0] for r in rows]


async def _audit_row(engine: AsyncEngine, at: datetime) -> None:
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO audit_log (action, at) VALUES ('t.x', :at)"), {"at": at})


async def _where(engine: AsyncEngine, parent: str) -> dict[str, int]:
    async with engine.connect() as conn:
        rows = await conn.execute(text(f"SELECT tableoid::regclass::text, count(*) FROM {parent} GROUP BY 1"))  # noqa: S608
        return {r[0]: r[1] for r in rows}


async def test__migrated__parent_is_partitioned_with_legacy_monthly_and_default(
    pg_migrated_engine: AsyncEngine,
) -> None:
    for parent in ("audit_log", "ai_usage"):
        names = await _names(pg_migrated_engine, parent)
        assert names[0] == f"{parent}_legacy"
        assert names[-1] == f"{parent}_default"
        assert len(names) >= 4  # legacy, несколько месяцев вперёд, default
        assert all(n.startswith(f"{parent}_p") for n in names[1:-1])


async def test__rows__route_to_legacy_monthly_or_default(pg_migrated_engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    await _audit_row(pg_migrated_engine, now - timedelta(days=500))
    await _audit_row(pg_migrated_engine, now + timedelta(days=75))
    await _audit_row(pg_migrated_engine, datetime(2099, 1, 1, tzinfo=UTC))

    placed = await _where(pg_migrated_engine, "audit_log")

    assert placed["audit_log_legacy"] == 1
    assert placed["audit_log_default"] == 1
    assert sum(v for k, v in placed.items() if k.startswith("audit_log_p")) == 1


async def test__ensure_partitions__idempotent_and_extends_horizon(pg_migrated_engine: AsyncEngine) -> None:
    source = _audit(pg_migrated_engine, months_ahead=2)
    before = await _names(pg_migrated_engine, "audit_log")

    assert await source.ensure_partitions() == 0
    assert await _names(pg_migrated_engine, "audit_log") == before

    wide = _audit(pg_migrated_engine, months_ahead=8)
    assert await wide.ensure_partitions() > 0
    assert len(await _names(pg_migrated_engine, "audit_log")) > len(before)
    assert await wide.ensure_partitions() == 0


async def test__purge__drops_whole_old_partitions_without_delete(pg_migrated_engine: AsyncEngine) -> None:
    source = _audit(pg_migrated_engine)
    now = datetime.now(UTC)
    await _audit_row(pg_migrated_engine, now + timedelta(days=45))
    names = await _names(pg_migrated_engine, "audit_log")
    monthly = [n for n in names if "_p2" in n]
    assert monthly

    # Граница в будущем накрывает legacy и ближайшие месячные партиции целиком.
    result = await source.purge(_ctx(now + timedelta(days=62)))

    after = await _names(pg_migrated_engine, "audit_log")
    assert result.partitions_dropped >= 2
    assert "audit_log_legacy" not in after
    assert "audit_log_default" in after
    assert monthly[0] not in after
    assert (await source.measure()).partitions == len(after)


async def test__purge__legacy_rows_deleted_in_batches_by_cutoff(pg_migrated_engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    for days in (400, 390, 380, 10, 5):
        await _audit_row(pg_migrated_engine, now - timedelta(days=days))
    source = _audit(pg_migrated_engine)

    result = await source.purge(_ctx(now - timedelta(days=365), batch=2))

    assert result.removed == 3
    assert result.partitions_dropped == 0
    placed = await _where(pg_migrated_engine, "audit_log")
    assert placed == {"audit_log_legacy": 2}


async def test__purge__no_cutoff__only_ensures_partitions(pg_migrated_engine: AsyncEngine) -> None:
    await _audit_row(pg_migrated_engine, datetime.now(UTC) - timedelta(days=900))

    result = await _audit(pg_migrated_engine).purge(_ctx(None))

    assert (result.removed, result.partitions_dropped) == (0, 0)
    assert await _where(pg_migrated_engine, "audit_log") == {"audit_log_legacy": 1}


async def test__purge__deadline_reached__reports_more_and_resumes(pg_migrated_engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    for days in (500, 450, 400):
        await _audit_row(pg_migrated_engine, now - timedelta(days=days))
    source = _audit(pg_migrated_engine)
    expired = PurgeContext(now=now, cutoff=now - timedelta(days=365), batch_size=1, deadline=time.monotonic() - 1)

    first = await source.purge(expired)
    second = await source.purge(_ctx(now - timedelta(days=365), batch=1))

    assert first.more
    assert first.removed == 0
    assert second.removed == 3
    assert not second.more


async def test__ai_usage__purge_deletes_old_rows_and_keeps_recent(pg_migrated_engine: AsyncEngine) -> None:
    now = datetime.now(UTC)
    async with pg_migrated_engine.begin() as conn:
        for days in (200, 100, 1):
            await conn.execute(
                text(
                    "INSERT INTO ai_usage (id, at, provider_id, provider_owner, model, operation, outcome) "
                    "VALUES (gen_random_uuid(), :at, gen_random_uuid(), 'instance', 'm', 'chat', 'ok')"
                ),
                {"at": now - timedelta(days=days)},
            )

    result = await _ai(pg_migrated_engine).purge(_ctx(now - timedelta(days=90), batch=1))

    assert result.removed == 2
    async with pg_migrated_engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM ai_usage"))).scalar_one() == 1


async def test__audit_log__stays_append_only_on_partitions(pg_migrated_engine: AsyncEngine) -> None:
    await _audit_row(pg_migrated_engine, datetime.now(UTC) + timedelta(days=40))
    names = [n for n in await _names(pg_migrated_engine, "audit_log") if "_p2" in n]

    for statement in (
        "UPDATE audit_log SET action = 'x'",
        "DELETE FROM audit_log",
        "TRUNCATE audit_log",
        f"TRUNCATE {names[0]}",
        f"DELETE FROM {names[0]}",
    ):
        with pytest.raises(DBAPIError, match="append-only"):
            async with pg_migrated_engine.begin() as conn:
                await conn.execute(text(statement))


async def test__managed_functions__refuse_other_tables(pg_migrated_engine: AsyncEngine) -> None:
    with pytest.raises(DBAPIError, match="not partition-managed"):
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text("SELECT lifecycle_drop_partitions_before('users', now())"))
    with pytest.raises(DBAPIError, match="not partition-managed"):
        async with pg_migrated_engine.begin() as conn:
            await conn.execute(text("SELECT lifecycle_ensure_partitions('users', 1)"))


async def test__anonymize__still_works_through_partitions(pg_migrated_engine: AsyncEngine) -> None:
    async with pg_migrated_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO audit_log (action, actor_id, details) VALUES ('a', 'u1', '{\"email\": \"x@y\"}')")
        )
        changed = (await conn.execute(text("SELECT audit_log_anonymize('u1', 'deleted:abc')"))).scalar_one()
        row = (await conn.execute(text("SELECT actor_id, details FROM audit_log"))).one()

    assert changed == 1
    assert row[0] == "deleted:abc"
    assert "email" not in row[1]


async def test__downgrade_then_upgrade__keeps_every_row(pg_db_factory) -> None:  # type: ignore[no-untyped-def]
    engine: AsyncEngine = await pg_db_factory()
    now = datetime.now(UTC)
    for days in (400, 10, -40, -4000):
        await _audit_row(engine, now - timedelta(days=days))
    async with engine.begin() as conn:
        before = (await conn.execute(text("SELECT id, action FROM audit_log ORDER BY id"))).all()

    await migrator.downgrade(engine, "s5_01_review")
    async with engine.connect() as conn:
        flat = (await conn.execute(text("SELECT id, action FROM audit_log ORDER BY id"))).all()
        kind = (
            await conn.execute(text("SELECT relkind::text FROM pg_class WHERE oid = 'audit_log'::regclass"))
        ).scalar_one()
        nxt = (await conn.execute(text("SELECT nextval('audit_log_id_seq')"))).scalar_one()
    assert flat == before
    assert kind == "r"
    assert nxt > max(r[0] for r in before)
    with pytest.raises(DBAPIError, match="append-only"):
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM audit_log"))

    await migrator.upgrade(engine)
    async with engine.connect() as conn:
        again = (await conn.execute(text("SELECT id, action FROM audit_log ORDER BY id"))).all()
        kind = (
            await conn.execute(text("SELECT relkind::text FROM pg_class WHERE oid = 'audit_log'::regclass"))
        ).scalar_one()
    assert again == before
    assert kind == "p"
    assert await migrator.check_drift(engine) == []


async def test__upgrade__existing_rows_survive_the_swap(pg_db_factory) -> None:  # type: ignore[no-untyped-def]
    engine: AsyncEngine = await pg_db_factory()
    await migrator.downgrade(engine, "s5_01_review")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO audit_log (action, at) "
                "SELECT 'old', now() - (g || ' days')::interval FROM generate_series(1, 300) g"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO ai_usage (id, at, provider_id, provider_owner, model, operation, outcome) "
                "SELECT gen_random_uuid(), now() - (g || ' days')::interval, gen_random_uuid(), "
                "'instance', 'm', 'chat', 'ok' FROM generate_series(1, 120) g"
            )
        )

    await migrator.upgrade(engine)

    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar_one() == 300
        assert (await conn.execute(text("SELECT count(*) FROM ai_usage"))).scalar_one() == 120
        # Новая запись продолжает последовательность, а не упирается в занятые id.
    await _audit_row(engine, datetime.now(UTC))
    async with engine.connect() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM audit_log"))).scalar_one() == 301
