"""Правила вердикта: факты и пороги на входе, статус и код причины на выходе. Без ввода-вывода."""

from __future__ import annotations

from hse_doc_studio.core.diagnostics.entities import DiagStatus, Verdict
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
    TlsFacts,
)
from hse_doc_studio.core.diagnostics.thresholds import DiagThresholds
from hse_doc_studio.core.lifecycle.disk import StorageLevel

_OK = DiagStatus.ok
_WARN = DiagStatus.warn
_FAIL = DiagStatus.fail
# Задача считается застывшей, если не отрабатывала столько интервалов подряд.
STALE_FACTOR = 3


def _by_level(value: float, warn: float, fail: float) -> DiagStatus:
    return _FAIL if value >= fail else _WARN if value >= warn else _OK


def judge_database(f: DbFacts, t: DiagThresholds) -> Verdict:
    if f.error is not None or f.latency_ms is None:
        return Verdict(_FAIL, "db_unreachable", {"error": f.error or "unknown"})
    values: dict[str, str | int | float] = {"latency_ms": round(f.latency_ms), "version": f.version or ""}
    status = _by_level(f.latency_ms, t.db_latency_warn_ms, t.db_latency_fail_ms)
    return Verdict(status, "db_slow" if status is not _OK else "ok", values)


def judge_migrations(f: MigrationFacts) -> Verdict:
    values = {"current": f.current or "", "head": f.head}
    if f.current == f.head:
        return Verdict(_OK, "ok", values)
    if f.current is None:
        return Verdict(_FAIL, "migrations_missing", values)
    if not f.known:
        return Verdict(_WARN, "migrations_ahead", values)
    return Verdict(_FAIL, "migrations_behind", values)


def judge_object_storage(f: ObjectFacts, t: DiagThresholds) -> Verdict:
    values: dict[str, str | int | float] = {"kind": f.kind, "bucket": f.bucket or ""}
    if f.error_stage is not None:
        reason = {
            "check": "object_unreachable",
            "write": "object_write_failed",
            "read": "object_read_failed",
            "mismatch": "object_mismatch",
        }.get(f.error_stage, "object_write_failed")
        return Verdict(_FAIL, reason, values)
    ms = f.roundtrip_ms or 0.0
    values["roundtrip_ms"] = round(ms)
    status = _by_level(ms, t.store_latency_warn_ms, t.store_latency_fail_ms)
    if status is _OK and f.outside_runners_blind:
        return Verdict(_WARN, "object_not_public", {**values, "runners": f.outside_runners_blind})
    return Verdict(status, "object_slow" if status is not _OK else "ok", values)


def judge_runners(f: RunnerFacts) -> Verdict:
    values = {"registered": f.registered, "online": f.online, "queued": f.queued}
    if f.registered == 0:
        return Verdict(_WARN, "no_runners", values)
    if f.online == 0:
        return Verdict(_FAIL if f.queued else _WARN, "no_online_runner", values)
    return Verdict(_OK, "ok", values)


def judge_jobs(f: JobFacts, t: DiagThresholds) -> Verdict:
    values = {
        "queued": f.queued,
        "oldest_wait_s": round(f.oldest_wait_s),
        "stuck": f.stuck,
        "oldest_overdue_s": round(f.oldest_overdue_s),
    }
    stuck = _OK
    if f.stuck:
        stuck = _by_level(f.oldest_overdue_s, t.stuck_job_warn_s, t.stuck_job_fail_s)
    wait = _by_level(f.oldest_wait_s, t.queue_wait_warn_s, t.queue_wait_fail_s) if f.queued else _OK
    if stuck is not _OK and stuck >= wait:
        return Verdict(stuck, "jobs_stuck", values)
    if wait is not _OK:
        return Verdict(wait, "queue_wait", values)
    return Verdict(_OK, "ok", values)


def judge_disk(f: DiskFacts) -> Verdict:
    values: dict[str, str | int | float] = {
        "volume": f.volume or "",
        "percent": f.percent if f.percent is not None else -1,
        "biggest_source": f.biggest_source or "",
        "safe_mode": int(f.safe_mode),
    }
    if f.level is StorageLevel.critical:
        return Verdict(_FAIL, "disk_critical", values)
    if f.level is StorageLevel.warning:
        return Verdict(_WARN, "disk_warning", values)
    if f.lifecycle_errors:
        return Verdict(_WARN, "lifecycle_failing", {**values, "errors": f.lifecycle_errors})
    return Verdict(_OK, "ok", values)


def _tls_expiry(days_left: int, t: DiagThresholds) -> tuple[DiagStatus, str]:
    if days_left < 0:
        return _FAIL, "tls_expired"
    if days_left <= t.tls_fail_days:
        return _FAIL, "tls_expiring"
    if days_left <= t.tls_warn_days:
        return _WARN, "tls_expiring"
    return _OK, "ok"


def judge_tls(f: TlsFacts, t: DiagThresholds) -> Verdict:
    if not f.configured:
        return Verdict(_OK, "not_configured")
    if not f.https:
        return Verdict(_OK, "no_tls", {"host": f.host or ""})
    values: dict[str, str | int | float] = {"host": f.host or ""}
    if f.error is not None or f.days_left is None:
        return Verdict(_WARN, "tls_unreachable", {**values, "error": f.error or "unknown"})
    status, reason = _tls_expiry(f.days_left, t)
    return Verdict(status, reason, {**values, "days_left": f.days_left})


def judge_backups(f: BackupFacts, t: DiagThresholds) -> Verdict:
    if not f.enabled:
        return Verdict(_WARN, "backups_disabled")
    if not f.has_destination:
        return Verdict(_WARN, "backups_no_destination")
    if f.last_ok_at is None or f.now is None:
        return Verdict(_WARN, "backups_never", {"last_failed": int(f.last_failed)})
    age_h = max(0.0, (f.now - f.last_ok_at).total_seconds() / 3600)
    values = {"age_hours": round(age_h, 1)}
    status = _by_level(age_h, t.backup_warn_hours, t.backup_fail_hours)
    if status is not _OK:
        return Verdict(status, "backups_stale", values)
    if f.last_failed:
        return Verdict(_WARN, "backups_last_failed", values)
    return Verdict(_OK, "ok", values)


def judge_smtp(f: SmtpFacts) -> Verdict:
    if not f.configured:
        return Verdict(_OK, "not_configured")
    if f.error is not None:
        return Verdict(_WARN, "smtp_unreachable", {"error": f.error})
    return Verdict(_OK, "ok", {"latency_ms": round(f.latency_ms or 0)})


def _task_problems(f: SchedulerFacts) -> tuple[list[str], list[str]]:
    stale: list[str] = []
    failing: list[str] = []
    for task in f.tasks:
        if task.runs and task.failures >= task.runs:
            failing.append(task.name)
        elif f.now and task.last_run_at:
            limit = max(STALE_FACTOR * task.interval_s, task.interval_s + 60)
            if (f.now - task.last_run_at).total_seconds() > limit:
                stale.append(task.name)
    return sorted(stale), sorted(failing)


def judge_scheduler(f: SchedulerFacts) -> Verdict:
    if not f.leader_present:
        return Verdict(_FAIL, "no_leader")
    if not f.leader_here:
        # Задачи идут в другом процессе: о нём говорит только метка прошлого прохода самодиагностики.
        if f.now and f.last_tick_at and (f.now - f.last_tick_at).total_seconds() > STALE_FACTOR * f.tick_interval_s:
            return Verdict(_WARN, "heartbeat_stale", {"seconds": int((f.now - f.last_tick_at).total_seconds())})
        return Verdict(_OK, "ok", {"leader_here": 0})
    stale, failing = _task_problems(f)
    if stale:
        return Verdict(_FAIL, "task_stale", {"tasks": ", ".join(stale)})
    if failing:
        return Verdict(_WARN, "task_failing", {"tasks": ", ".join(failing)})
    return Verdict(_OK, "ok", {"leader_here": 1, "tasks": len(f.tasks)})
