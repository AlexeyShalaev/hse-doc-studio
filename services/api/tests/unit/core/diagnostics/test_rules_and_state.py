"""Правила вердикта, пороги и антидребезг уведомлений самодиагностики."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.diagnostics import rules
from hse_doc_studio.core.diagnostics.entities import CHECKS, CheckResult, DiagStatus, overall
from hse_doc_studio.core.diagnostics.facts import (
    BackupFacts,
    DbFacts,
    DiskFacts,
    JobFacts,
    MigrationFacts,
    ObjectFacts,
    RunnerFacts,
    SchedulerFacts,
    SmtpFacts,
    TaskFact,
    TlsFacts,
)
from hse_doc_studio.core.diagnostics.state import (
    NOTICE_FAIL,
    NOTICE_RECOVERED,
    NOTICE_WARN,
    CheckState,
    advance,
)
from hse_doc_studio.core.diagnostics.thresholds import (
    BOUNDS,
    DEFAULTS,
    KEY_NOTIFY,
    KEY_PREFIX,
    misordered,
    thresholds_from,
)
from hse_doc_studio.core.lifecycle.disk import StorageLevel

T = DEFAULTS
NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
OK, WARN, FAIL = DiagStatus.ok, DiagStatus.warn, DiagStatus.fail


def test__registry__ids_unique_and_complete() -> None:
    ids = [c.id.value for c in CHECKS]
    assert len(ids) == len(set(ids))
    assert {"database", "migrations", "object_storage", "runners", "disk", "tls_public", "backups", "smtp"} <= set(ids)


@pytest.mark.parametrize(
    ("facts", "status", "reason"),
    [
        (DbFacts(latency_ms=5, version="16"), OK, "ok"),
        (DbFacts(latency_ms=400), WARN, "db_slow"),
        (DbFacts(latency_ms=2500), FAIL, "db_slow"),
        (DbFacts(error="OSError"), FAIL, "db_unreachable"),
    ],
)
def test__database__verdict(facts: DbFacts, status: DiagStatus, reason: str) -> None:
    verdict = rules.judge_database(facts, T)
    assert (verdict.status, verdict.reason) == (status, reason)


def test__migrations__verdicts() -> None:
    assert rules.judge_migrations(MigrationFacts("a", "a")).status is OK
    assert rules.judge_migrations(MigrationFacts(None, "a")).reason == "migrations_missing"
    assert rules.judge_migrations(MigrationFacts("b", "a", known=False)).reason == "migrations_ahead"
    assert rules.judge_migrations(MigrationFacts("old", "a")).reason == "migrations_behind"


@pytest.mark.parametrize(
    ("stage", "reason"),
    [
        ("check", "object_unreachable"),
        ("write", "object_write_failed"),
        ("read", "object_read_failed"),
        ("mismatch", "object_mismatch"),
    ],
)
def test__object_storage__failures(stage: str, reason: str) -> None:
    verdict = rules.judge_object_storage(ObjectFacts("s3", "b", error_stage=stage), T)
    assert (verdict.status, verdict.reason) == (FAIL, reason)


def test__object_storage__slow_roundtrip__warn() -> None:
    assert rules.judge_object_storage(ObjectFacts("fs", roundtrip_ms=3000), T).status is WARN
    assert rules.judge_object_storage(ObjectFacts("fs", roundtrip_ms=20), T).status is OK


def test__object_storage__outside_runners_without_public_address__warns_with_count() -> None:
    verdict = rules.judge_object_storage(ObjectFacts("s3", "b", roundtrip_ms=20, outside_runners_blind=2), T)

    assert (verdict.status, verdict.reason) == (WARN, "object_not_public")
    assert verdict.values["runners"] == 2


def test__object_storage__no_outside_runners__ok_and_failure_wins_over_the_warning() -> None:
    assert rules.judge_object_storage(ObjectFacts("s3", "b", roundtrip_ms=20), T).status is OK
    broken = rules.judge_object_storage(ObjectFacts("s3", "b", error_stage="check", outside_runners_blind=2), T)
    assert (broken.status, broken.reason) == (FAIL, "object_unreachable")


def test__runners__verdicts() -> None:
    assert rules.judge_runners(RunnerFacts()).reason == "no_runners"
    assert rules.judge_runners(RunnerFacts(registered=2, online=0, queued=0)).status is WARN
    assert rules.judge_runners(RunnerFacts(registered=2, online=0, queued=3)).status is FAIL
    assert rules.judge_runners(RunnerFacts(registered=2, online=1)).status is OK


def test__jobs__stuck_and_queue() -> None:
    assert rules.judge_jobs(JobFacts(), T).status is OK
    assert rules.judge_jobs(JobFacts(stuck=1, oldest_overdue_s=400), T).status is WARN
    assert rules.judge_jobs(JobFacts(stuck=1, oldest_overdue_s=4000), T).reason == "jobs_stuck"
    waiting = rules.judge_jobs(JobFacts(queued=2, oldest_wait_s=700), T)
    assert (waiting.status, waiting.reason) == (WARN, "queue_wait")
    assert rules.judge_jobs(JobFacts(queued=0, oldest_wait_s=9999), T).status is OK


def test__disk__levels_and_lifecycle_errors() -> None:
    assert rules.judge_disk(DiskFacts(StorageLevel.critical, "data", 95)).status is FAIL
    assert rules.judge_disk(DiskFacts(StorageLevel.warning, "data", 85)).reason == "disk_warning"
    assert rules.judge_disk(DiskFacts(lifecycle_errors=2)).reason == "lifecycle_failing"
    assert rules.judge_disk(DiskFacts()).status is OK


def test__tls__verdicts() -> None:
    assert rules.judge_tls(TlsFacts(configured=False), T).reason == "not_configured"
    assert rules.judge_tls(TlsFacts(configured=True, https=False, host="h"), T).reason == "no_tls"
    assert rules.judge_tls(TlsFacts(configured=True, host="h", error="x"), T).status is WARN
    assert rules.judge_tls(TlsFacts(configured=True, host="h", days_left=90), T).status is OK
    assert rules.judge_tls(TlsFacts(configured=True, host="h", days_left=15), T).status is WARN
    assert rules.judge_tls(TlsFacts(configured=True, host="h", days_left=3), T).status is FAIL
    assert rules.judge_tls(TlsFacts(configured=True, host="h", days_left=-1), T).reason == "tls_expired"


def test__backups__verdicts() -> None:
    day = timedelta(hours=1)
    base = {"enabled": True, "has_destination": True, "now": NOW}
    assert rules.judge_backups(BackupFacts(enabled=False, has_destination=True), T).reason == "backups_disabled"
    assert rules.judge_backups(BackupFacts(enabled=True, has_destination=False), T).reason == "backups_no_destination"
    assert rules.judge_backups(BackupFacts(**base), T).reason == "backups_never"  # type: ignore[arg-type]
    fresh = BackupFacts(**base, last_ok_at=NOW - 5 * day)  # type: ignore[arg-type]
    assert rules.judge_backups(fresh, T).status is OK
    assert rules.judge_backups(BackupFacts(**base, last_ok_at=NOW - 40 * day), T).status is WARN  # type: ignore[arg-type]
    assert rules.judge_backups(BackupFacts(**base, last_ok_at=NOW - 100 * day), T).status is FAIL  # type: ignore[arg-type]
    failed = BackupFacts(**base, last_ok_at=NOW - 5 * day, last_failed=True)  # type: ignore[arg-type]
    assert rules.judge_backups(failed, T).reason == "backups_last_failed"


def test__smtp__verdicts() -> None:
    assert rules.judge_smtp(SmtpFacts(configured=False)).reason == "not_configured"
    assert rules.judge_smtp(SmtpFacts(configured=True, error="TimeoutError")).status is WARN
    assert rules.judge_smtp(SmtpFacts(configured=True, latency_ms=30)).status is OK


def test__scheduler__verdicts() -> None:
    assert rules.judge_scheduler(SchedulerFacts(leader_present=False, leader_here=False)).status is FAIL
    fine = TaskFact("x", 60, 5, 0, NOW - timedelta(seconds=30))
    assert rules.judge_scheduler(SchedulerFacts(True, True, [fine], now=NOW)).status is OK
    stale = TaskFact("x", 60, 5, 0, NOW - timedelta(hours=1))
    assert rules.judge_scheduler(SchedulerFacts(True, True, [stale], now=NOW)).reason == "task_stale"
    broken = TaskFact("y", 60, 4, 4, NOW)
    assert rules.judge_scheduler(SchedulerFacts(True, True, [broken], now=NOW)).reason == "task_failing"
    old = NOW - timedelta(hours=2)
    away = SchedulerFacts(True, False, last_tick_at=old, tick_interval_s=300, now=NOW)
    assert rules.judge_scheduler(away).reason == "heartbeat_stale"


def test__thresholds__defaults_bounds_and_pairs() -> None:
    assert thresholds_from({}) == DEFAULTS
    custom = thresholds_from({KEY_PREFIX + "tls_warn_days": 30, KEY_NOTIFY: False})
    assert custom.tls_warn_days == 30
    assert custom.notify is False
    assert thresholds_from({KEY_PREFIX + "tls_warn_days": 99999}).tls_warn_days == DEFAULTS.tls_warn_days
    assert thresholds_from({KEY_PREFIX + "tls_warn_days": True}).tls_warn_days == DEFAULTS.tls_warn_days
    # Нарушенный порядок пары: обе границы возвращаются к умолчанию.
    broken = thresholds_from({KEY_PREFIX + "db_latency_warn_ms": 5000, KEY_PREFIX + "db_latency_fail_ms": 100})
    assert (broken.db_latency_warn_ms, broken.db_latency_fail_ms) == (300, 2000)
    assert misordered(_all()) == []
    assert misordered({**_all(), "tls_warn_days": 3, "tls_fail_days": 7}) == [("tls_warn_days", "tls_fail_days")]


def _all() -> dict[str, int]:
    return {n: int(getattr(DEFAULTS, n)) for n in BOUNDS}


def _result(status: DiagStatus, at: datetime = NOW, reason: str = "r") -> CheckResult:
    return CheckResult("database", status, reason, {}, at, 1)


def _run(statuses: list[DiagStatus], confirm: int = 2) -> list[str | None]:
    state: CheckState | None = None
    notices: list[str | None] = []
    for i, status in enumerate(statuses):
        at = NOW + timedelta(minutes=5 * i)
        state, notice = advance(state, _result(status, at), confirm_runs=confirm, repeat=timedelta(hours=24), now=at)
        notices.append(notice)
    return notices


def test__advance__needs_confirmation_before_notice() -> None:
    assert _run([FAIL, FAIL, FAIL]) == [None, NOTICE_FAIL, None]


def test__advance__flapping_never_notifies() -> None:
    assert _run([FAIL, OK, FAIL, OK, WARN, OK]) == [None] * 6


def test__advance__recovery_only_after_notice_and_confirmed() -> None:
    assert _run([FAIL, FAIL, OK, OK]) == [None, NOTICE_FAIL, None, NOTICE_RECOVERED]
    assert _run([OK, OK, OK]) == [None, None, None]


def test__advance__status_change_notifies_again() -> None:
    assert _run([WARN, WARN, FAIL, FAIL]) == [None, NOTICE_WARN, None, NOTICE_FAIL]


def test__advance__reminder_after_repeat_interval() -> None:
    state: CheckState | None = None
    out = []
    for hours in (0, 1, 2, 25, 26):
        at = NOW + timedelta(hours=hours)
        state, notice = advance(state, _result(FAIL, at), confirm_runs=2, repeat=timedelta(hours=24), now=at)
        out.append(notice)
    assert out == [None, NOTICE_FAIL, None, NOTICE_FAIL, None]


def test__advance__tracks_status_since() -> None:
    first = NOW
    state, _ = advance(None, _result(FAIL, first), confirm_runs=2, repeat=timedelta(hours=1), now=first)
    later = NOW + timedelta(minutes=10)
    state, _ = advance(state, _result(FAIL, later), confirm_runs=2, repeat=timedelta(hours=1), now=later)
    assert (state.status_since, state.streak) == (first, 2)
    back = NOW + timedelta(minutes=20)
    state, _ = advance(state, _result(OK, back), confirm_runs=2, repeat=timedelta(hours=1), now=back)
    assert (state.status_since, state.streak) == (back, 1)


def test__overall__worst_status() -> None:
    assert overall([]) is OK
    assert overall([_result(OK), _result(WARN), _result(OK)]) is WARN
    assert overall([_result(WARN), _result(FAIL)]) is FAIL


def test__result__hint_only_when_not_ok() -> None:
    assert _result(OK, reason="ok").hint is None
    assert _result(WARN, reason="disk_warning").hint == "disk_warning"
    assert _result(OK, reason="not_configured").applicable is False
