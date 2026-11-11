"""«Освободить место» на Postgres: таблица прогонов, счёт предпросмотра с потолком и таймаутом, прогон целиком."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from dishka import AsyncContainer
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.lifecycle.sweeps import LifecycleSweep, StepStatus, SweepStatus, SweepStep
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.lifecycle_sweeps import SqlLifecycleSweeps
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.lifecycle import sql_sources
from hse_doc_studio.infra.lifecycle.sql_sources import count_capped
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from hse_doc_studio.use_cases.lifecycle.sweep import LifecycleSweepService
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

ADMIN = Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)
T0 = datetime(2026, 11, 16, 12, tzinfo=UTC)


@pytest_asyncio.fixture
async def container(pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)
    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    c = create_container(StudioMode.server, engine=pg_migrated_engine)
    yield c
    await c.close()


def _repo(engine: AsyncEngine) -> SqlLifecycleSweeps:
    return SqlLifecycleSweeps(SessionProvider(create_sessionmaker(engine)))


async def _user(engine: AsyncEngine, uid: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, email_normalized, name, status, is_instance_admin, created_at) "
                "VALUES (:i, :e, :e, :i, 'active', true, now())"
            ),
            {"i": uid, "e": f"{uid}@x.org"},
        )


async def _notifications(engine: AsyncEngine, uid: str, count: int, age_days: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO notifications (id, user_id, kind, payload, created_at) "
                "SELECT :p || g, :u, 'member_removed', '{}', now() - make_interval(days => CAST(:d AS int)) "
                "FROM generate_series(1, :n) AS g"
            ),
            {"p": f"n-{age_days}-", "u": uid, "n": count, "d": age_days},
        )


async def _guest(engine: AsyncEngine, gid: str, expires_in_days: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO guest_sessions (id, secret_hash, created_at, last_seen_at, expires_at, csrf_token) "
                "VALUES (:i, :i, now(), now(), now() + make_interval(days => :d), 'c')"
            ),
            {"i": gid, "d": expires_in_days},
        )


def _sweep(started: datetime, status: SweepStatus = SweepStatus.done, *, by: str | None = None) -> LifecycleSweep:
    return LifecycleSweep(
        id=str(uuid4()),
        status=status,
        started_by=by,
        started_at=started,
        updated_at=started,
        finished_at=None if status.active else started,
        steps=(SweepStep("notifications"), SweepStep("jobs")),
    )


async def test__repo__single_active_sweep_and_last_20_kept(pg_migrated_engine: AsyncEngine) -> None:
    repo = _repo(pg_migrated_engine)
    old = [_sweep(T0 + timedelta(minutes=n)) for n in range(22)]
    for sweep in old:
        assert await repo.create(sweep, keep=20)
    live = _sweep(T0 + timedelta(hours=1), SweepStatus.running)

    created = await repo.create(live, keep=20)
    second = await repo.create(_sweep(T0 + timedelta(hours=2), SweepStatus.running), keep=20)
    cancelling = await repo.request_cancel(live.id, at=T0)
    third = await repo.create(_sweep(T0 + timedelta(hours=3), SweepStatus.running), keep=20)

    assert created
    assert not second
    assert cancelling is not None
    assert cancelling.status is SweepStatus.cancelling
    assert not third, "отменяемый прогон ещё идёт: второй запускать нельзя"
    async with pg_migrated_engine.connect() as conn:
        total = (await conn.execute(text("SELECT count(*) FROM lifecycle_sweeps"))).scalar_one()
    assert total == 20
    assert await repo.get(old[0].id) is None
    latest = await repo.latest()
    assert latest is not None
    assert latest.id == live.id


async def test__repo__progress_finish_and_stale_interrupt(pg_migrated_engine: AsyncEngine) -> None:
    await _user(pg_migrated_engine, "boss")
    repo = _repo(pg_migrated_engine)
    live = _sweep(T0, SweepStatus.running, by="boss")
    await repo.create(live, keep=20)
    steps = [SweepStep("notifications", StepStatus.done, removed=4, bytes_before=10, bytes_after=4), SweepStep("jobs")]

    status = await repo.save_steps(live.id, steps, at=T0 + timedelta(minutes=1))
    fresh = await repo.interrupt_stale(before=T0, at=T0 + timedelta(minutes=2))
    running = [steps[0], SweepStep("jobs", StepStatus.running)]
    await repo.save_steps(live.id, running, at=T0 + timedelta(minutes=2))
    stale = await repo.interrupt_stale(before=T0 + timedelta(minutes=10), at=T0 + timedelta(minutes=11))
    late = await repo.finish(live.id, SweepStatus.done, running, at=T0 + timedelta(minutes=12))
    after = await repo.save_steps(live.id, running, at=T0 + timedelta(minutes=12))
    stored = await repo.get(live.id)

    assert status is SweepStatus.running
    assert fresh == []
    assert [s.id for s in stale] == [live.id]
    assert late is None, "закрытый прогон итогом не перезаписывается"
    assert after is SweepStatus.interrupted
    assert stored is not None
    assert stored.status is SweepStatus.interrupted
    assert stored.started_by == "boss"
    assert stored.finished_at == T0 + timedelta(minutes=11)
    assert [(s.key, s.status, s.removed) for s in stored.steps] == [
        ("notifications", StepStatus.done, 4),
        ("jobs", StepStatus.error, 0),
    ]
    assert stored.freed_bytes == 6
    assert await repo.request_cancel("not-a-uuid", at=T0) is None


async def test__count_expired__real_sources_with_cap(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    await _user(pg_migrated_engine, "anna")
    await _notifications(pg_migrated_engine, "anna", 7, 200)
    await _notifications(pg_migrated_engine, "anna", 2, 1)
    await _guest(pg_migrated_engine, "g-gone", -30)
    await _guest(pg_migrated_engine, "g-grace", -1)
    engine = await container.get(LifecycleEngine)

    notifications = await engine.count_expired("notifications", cap=100)
    capped = await engine.count_expired("notifications", cap=5)
    guests = await engine.count_expired("guest_sessions", cap=100)
    jobs = await engine.count_expired("jobs", cap=100)
    ai = await engine.count_expired("ai_usage", cap=100)

    assert notifications.count == 7
    assert capped.count == 6
    assert guests.count == 1
    assert guests.cutoff is not None
    assert (jobs.count, ai.count) == (0, 0)


async def test__count_capped__statement_timeout__none(
    pg_migrated_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sql_sources, "COUNT_TIMEOUT_MS", 50)
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))

    slow = await count_capped(sessions, [text("SELECT count(*) FROM (SELECT pg_sleep(2) LIMIT :limit) AS s")], {}, 10)
    fast = await count_capped(sessions, [text("SELECT 3 + 0 * :limit")], {}, 10)

    assert slow is None
    assert fast == 3


async def test__service__preview_and_sweep_on_real_container(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    await _user(pg_migrated_engine, "boss")
    await _user(pg_migrated_engine, "anna")
    await _notifications(pg_migrated_engine, "anna", 3, 200)
    service = await container.get(LifecycleSweepService)

    preview = await service.preview(ADMIN)
    started = await service.start(ADMIN)
    await service.drain()
    sweep = await service.current(ADMIN)

    counts = {s.key: s.count for s in preview.sources}
    assert counts["notifications"] == 3
    assert not preview.nothing
    assert sweep is not None
    assert sweep.id == started.id
    assert sweep.status is SweepStatus.done
    assert {s.key: s.removed for s in sweep.steps}["notifications"] == 3
    assert (await service.preview(ADMIN)).nothing
    async with pg_migrated_engine.connect() as conn:
        actions = (
            (await conn.execute(text("SELECT action FROM audit_log WHERE action LIKE 'lifecycle.sw%' ORDER BY id")))
            .scalars()
            .all()
        )
    assert actions == ["lifecycle.sweep", "lifecycle.swept"]
