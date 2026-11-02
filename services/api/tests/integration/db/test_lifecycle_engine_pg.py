"""Движок жизненного цикла на настоящем DI-контейнере и Postgres: очистка таблиц, статистика, срок из админки, места."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from dishka import AsyncContainer
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.identity.errors import IdentityError
from hse_doc_studio.core.invitations.entities import NotificationKind
from hse_doc_studio.core.invitations.protocols import INotificationRepository, INotifier
from hse_doc_studio.core.lifecycle.disk import SafeMode, StorageLevel
from hse_doc_studio.core.lifecycle.ports import IAdminDirectory, ILifecycleRuns, VolumeUsage
from hse_doc_studio.core.listing import Window
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.lifecycle.probe import StorageProbe
from hse_doc_studio.use_cases.lifecycle.admin import GetLifecycleUC, RunLifecycleUC, UpdateRetentionUC
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

ADMIN = Actor(kind=ActorKind.user, id="boss", is_instance_admin=True)


@pytest_asyncio.fixture
async def container(pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)
    monkeypatch.setattr(settings.secrets, "key", SecretStr(Fernet.generate_key().decode()))
    c = create_container(StudioMode.server, engine=pg_migrated_engine)
    yield c
    await c.close()


async def _user(engine: AsyncEngine, uid: str, *, admin: bool = False, status: str = "active") -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, email_normalized, name, status, is_instance_admin, created_at) "
                "VALUES (:i, :e, :e, :i, :s, :a, now())"
            ),
            {"i": uid, "e": f"{uid}@x.org", "s": status, "a": admin},
        )


async def _notification(engine: AsyncEngine, nid: str, uid: str, age_days: int) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO notifications (id, user_id, kind, payload, created_at) "
                "VALUES (:i, :u, 'member_removed', '{}', now() - make_interval(days => :d))"
            ),
            {"i": nid, "u": uid, "d": age_days},
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


async def _count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())  # noqa: S608


async def test__run_all__cleans_every_source_and_records_stats(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    await _user(pg_migrated_engine, "anna")
    await _notification(pg_migrated_engine, "n-old", "anna", 200)
    await _notification(pg_migrated_engine, "n-new", "anna", 1)
    await _guest(pg_migrated_engine, "g-gone", -30)
    await _guest(pg_migrated_engine, "g-grace", -1)
    await _guest(pg_migrated_engine, "g-live", 5)
    engine = await container.get(LifecycleEngine)

    outcomes = await engine.run_all()

    assert [o.error for o in outcomes] == [None] * len(outcomes)
    assert await _count(pg_migrated_engine, "notifications") == 1
    assert await _count(pg_migrated_engine, "guest_sessions") == 2
    runs = await (await container.get(ILifecycleRuns)).all()
    assert runs["notifications"].last_removed == 1
    assert runs["guest_sessions"].last_removed == 1
    assert {"audit_log", "ai_usage", "jobs", "collab_state"} <= set(runs)


async def test__admin_retention__controls_what_notifications_survive(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    await _user(pg_migrated_engine, "boss", admin=True)
    await _user(pg_migrated_engine, "anna")
    await _notification(pg_migrated_engine, "n-old", "anna", 200)
    await (await container.get(UpdateRetentionUC)).execute(ADMIN, "notifications", 365)

    outcome = await (await container.get(RunLifecycleUC)).execute(ADMIN, "notifications")

    assert outcome.removed == 0
    assert await _count(pg_migrated_engine, "notifications") == 1
    await (await container.get(UpdateRetentionUC)).execute(ADMIN, "notifications", 30)
    outcome = await (await container.get(RunLifecycleUC)).execute(ADMIN, "notifications")
    assert outcome.removed == 1
    with pytest.raises(IdentityError):
        await (await container.get(UpdateRetentionUC)).execute(ADMIN, "audit_log", 5)


async def test__overview__sizes_stats_and_audit_events(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    await _user(pg_migrated_engine, "boss", admin=True)
    await (await container.get(LifecycleEngine)).run_one("notifications")

    view = await (await container.get(GetLifecycleUC)).execute(ADMIN)

    by_key = {s.policy.key: s for s in view.sources}
    assert by_key["audit_log"].size is not None
    assert by_key["audit_log"].size.partitions >= 4
    assert by_key["notifications"].last_run is not None
    assert by_key["compile_records"].size is not None
    names = [v.usage.name for v in view.volumes]
    assert names[-1] == "database"
    assert names[0].startswith("data")
    assert view.safe_mode is False


async def test__guard__alert_reaches_admin_inbox_once_a_day_and_safe_mode_follows(
    container: AsyncContainer, pg_migrated_engine: AsyncEngine
) -> None:
    await _user(pg_migrated_engine, "boss", admin=True)
    await _user(pg_migrated_engine, "anna")
    await _user(pg_migrated_engine, "off", admin=True, status="disabled")

    class Probe:
        ratio = 0.93

        async def volumes(self) -> list[VolumeUsage]:
            return [VolumeUsage("data", 93, 100, 7)]

        async def database_bytes(self) -> int:
            return 1

    mode = SafeMode()
    guard = StorageGuard(
        Probe(),
        await container.get(
            __import__("hse_doc_studio.core.identity.protocols", fromlist=["x"]).IInstanceSettingsRepository
        ),
        await container.get(INotifier),
        await container.get(IAdminDirectory),
        mode,
        safe_mode_enabled=True,
    )

    assert await guard.tick() is StorageLevel.critical
    assert await guard.tick() is StorageLevel.critical

    repo = await container.get(INotificationRepository)
    admin_items = (await repo.page("boss", unread_only=False, window=Window(limit=10, offset=0))).items
    assert [(n.kind, n.payload.outcome, n.payload.ref_id, n.payload.excerpt) for n in admin_items] == [
        (NotificationKind.system_alert, "storage_critical", "data", "93")
    ]
    assert (await repo.page("anna", unread_only=False, window=Window(limit=10, offset=0))).items == []
    assert (await repo.page("off", unread_only=False, window=Window(limit=10, offset=0))).items == []
    assert mode.active


async def test__probe__reports_database_and_data_volume(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> None:
    probe = StorageProbe(
        SessionProvider(create_sessionmaker(pg_migrated_engine)), [("data", tmp_path)], db_size_limit_bytes=10**12
    )

    volumes = {v.name: v for v in await probe.volumes()}

    assert volumes["data"].total_bytes
    assert 0 <= (volumes["data"].used_ratio or 0) <= 1
    assert volumes["database"].used_bytes > 0
    assert 0 < (volumes["database"].used_ratio or 0) < 1


async def test__lifecycle_runs__upsert_accumulates(container: AsyncContainer) -> None:
    runs = await container.get(ILifecycleRuns)
    now = datetime.now(UTC)

    await runs.record("x", at=now, duration_ms=5, removed=3, error=None)
    await runs.record("x", at=now + timedelta(seconds=1), duration_ms=7, removed=4, error="boom")

    stat = (await runs.all())["x"]
    assert (stat.runs, stat.total_removed, stat.last_removed, stat.last_error, stat.last_duration_ms) == (
        2,
        7,
        4,
        "boom",
        7,
    )
