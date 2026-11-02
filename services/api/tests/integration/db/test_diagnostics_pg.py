"""Самодиагностика на настоящем Postgres: хранилище состояния, пробы базы, миграций и лидера, схема в цепочке."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.background import BackgroundTaskRunner, PeriodicTask
from hse_doc_studio.core.diagnostics import rules
from hse_doc_studio.core.diagnostics.entities import CheckResult, DiagStatus
from hse_doc_studio.core.diagnostics.state import CheckState
from hse_doc_studio.core.diagnostics.thresholds import DEFAULTS
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.leader import PgAdvisoryLeaderLock
from hse_doc_studio.infra.db.migrator import head_revision
from hse_doc_studio.infra.db.repositories.diagnostics import SqlDiagStore
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.diagnostics.probes import (
    BackupProbe,
    DatabaseProbe,
    JobProbe,
    MigrationProbe,
    SchedulerProbe,
)
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def _sessions(engine: AsyncEngine) -> SessionProvider:
    return SessionProvider(create_sessionmaker(engine))


def _state(status: DiagStatus, **kw: object) -> CheckState:
    result = CheckResult("database", status, "r", {"latency_ms": 4, "version": "16"}, NOW, 7)
    return CheckState(result, NOW - timedelta(hours=1), **kw)  # type: ignore[arg-type]


async def test__store__upsert_roundtrip_keeps_values_and_notification_marks(pg_migrated_engine: AsyncEngine) -> None:
    store = SqlDiagStore(_sessions(pg_migrated_engine))

    await store.save(_state(DiagStatus.warn, streak=3, notified_status=DiagStatus.warn, notified_at=NOW))
    await store.save(_state(DiagStatus.fail, streak=1))

    loaded = (await store.load())["database"]
    assert loaded.result.status is DiagStatus.fail
    assert dict(loaded.result.values) == {"latency_ms": 4, "version": "16"}
    assert (loaded.streak, loaded.notified_status, loaded.result.duration_ms) == (1, None, 7)


async def test__database_and_migration_probes__healthy_install(pg_migrated_engine: AsyncEngine) -> None:
    sessions = _sessions(pg_migrated_engine)

    db = await DatabaseProbe(sessions).measure()
    migration = await MigrationProbe(sessions).read()

    assert db.error is None
    assert db.version
    assert rules.judge_database(db, DEFAULTS).status is DiagStatus.ok
    assert migration.current == migration.head == head_revision()
    assert rules.judge_migrations(migration).status is DiagStatus.ok


async def test__job_and_backup_probes__empty_install(pg_migrated_engine: AsyncEngine) -> None:
    from hse_doc_studio.infra.db.repositories.queue_metrics import SqlQueueMetricsReader  # noqa: PLC0415

    sessions = _sessions(pg_migrated_engine)

    jobs = await JobProbe(sessions, SqlQueueMetricsReader(sessions)).read(NOW)
    backups = BackupProbe(sessions)

    assert (jobs.stuck, jobs.queued) == (0, 0)
    assert await backups.last_ok_at() is None
    assert await backups.last_failed() is False


async def test__scheduler_probe__sees_leader_lock_from_any_connection(pg_migrated_engine: AsyncEngine) -> None:
    sessions = _sessions(pg_migrated_engine)
    runner = BackgroundTaskRunner()
    runner.register(PeriodicTask(name="t", interval_s=60, run=_noop))
    probe = SchedulerProbe(sessions, lambda: runner)

    assert (await probe.read(NOW)).leader_present is False

    lock = PgAdvisoryLeaderLock(pg_migrated_engine)
    assert await lock.acquire()
    try:
        facts = await probe.read(NOW)
        assert facts.leader_present is True
        assert facts.leader_here is False  # раннер этого процесса лидером не стал
    finally:
        await lock.release()


async def _noop() -> None:
    return None
