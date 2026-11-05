"""Осознанное принятие предупреждений: что можно принять, срок действия, разбор записей, итог без принятых."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.diagnostics.acceptance import (
    ACCEPTABLE,
    KEY_ACCEPTED,
    Acceptance,
    acceptances_from,
    acceptances_to,
    applies,
    is_acceptable,
    live_acceptance,
)
from hse_doc_studio.core.diagnostics.entities import CHECKS, CheckResult, DiagStatus, overall

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
NEVER = frozenset({"database", "migrations", "disk", "jobs", "scheduler"})


def _result(check: str, status: DiagStatus, reason: str) -> CheckResult:
    return CheckResult(check, status, reason, {}, NOW, 1)


def _acc(check: str = "backups", until: datetime | None = None) -> Acceptance:
    return Acceptance(check, "не делаю сознательно", "u1", "Анна", NOW, until)


def test__acceptable__only_known_checks_and_never_the_data_and_safety_ones() -> None:
    assert set(ACCEPTABLE) <= {spec.id.value for spec in CHECKS}
    assert not NEVER & set(ACCEPTABLE)


@pytest.mark.parametrize(
    ("check", "reason"),
    [(c, r) for c, reasons in ACCEPTABLE.items() for r in sorted(reasons)],
)
def test__is_acceptable__warn_with_listed_reason(check: str, reason: str) -> None:
    assert is_acceptable(check, DiagStatus.warn, reason)
    assert not is_acceptable(check, DiagStatus.fail, reason)
    assert not is_acceptable(check, DiagStatus.ok, reason)


@pytest.mark.parametrize(
    ("check", "reason"),
    [
        ("database", "db_slow"),
        ("migrations", "migrations_ahead"),
        ("disk", "disk_warning"),
        ("disk", "lifecycle_failing"),
        ("jobs", "queue_wait"),
        ("scheduler", "task_failing"),
        ("tls_public", "tls_expiring"),
        ("tls_s3", "tls_expired"),
        ("backups", "backups_stale"),
        ("backups", "backups_last_failed"),
        ("runners", "jobs_stuck"),
        ("smtp", "backups_disabled"),
    ],
)
def test__is_acceptable__critical_or_foreign_reason_is_refused_even_as_warn(check: str, reason: str) -> None:
    assert not is_acceptable(check, DiagStatus.warn, reason)


def test__live__no_until_is_forever_and_until_is_exclusive() -> None:
    assert _acc().live(NOW + timedelta(days=3650))
    soon = _acc(until=NOW + timedelta(hours=1))
    assert soon.live(NOW + timedelta(minutes=59))
    assert not soon.live(NOW + timedelta(hours=1))


def test__applies__needs_live_record_and_acceptable_state() -> None:
    warn = _result("backups", DiagStatus.warn, "backups_disabled")
    assert applies(_acc(), warn, NOW)
    assert not applies(_acc(until=NOW - timedelta(seconds=1)), warn, NOW)
    assert not applies(_acc(), _result("backups", DiagStatus.ok, "ok"), NOW)  # причину исправили: запись молчит
    assert not applies(_acc(), _result("backups", DiagStatus.fail, "backups_stale"), NOW)


def test__storage__round_trip_and_garbage_is_skipped() -> None:
    items = {"backups": _acc(), "runners": _acc("runners", NOW + timedelta(days=1))}
    stored = {KEY_ACCEPTED: acceptances_to(items)}

    assert acceptances_from(stored) == items

    junk = {
        KEY_ACCEPTED: {
            "backups": {"reason": 5, "by": "u", "at": NOW.isoformat()},
            "database": {"reason": "x", "by": "u", "at": NOW.isoformat()},  # принять нельзя: игнорируется
            "smtp": {"reason": "x", "by": "u", "at": "вчера"},
            "runners": "строка",
            "tls_s3": {"reason": "ok", "by": "u", "at": NOW.isoformat(), "until": "не дата"},
        }
    }
    parsed = acceptances_from(junk)
    assert set(parsed) == {"tls_s3"}
    assert parsed["tls_s3"].until is None
    assert acceptances_from({KEY_ACCEPTED: "мусор"}) == {}
    assert acceptances_from({}) == {}


def test__live_acceptance__ignores_expired() -> None:
    stored = {KEY_ACCEPTED: acceptances_to({"backups": _acc(until=NOW + timedelta(hours=1))})}
    assert live_acceptance(stored, "backups", NOW) is not None
    assert live_acceptance(stored, "backups", NOW + timedelta(hours=2)) is None
    assert live_acceptance(stored, "runners", NOW) is None


def test__overall__accepted_checks_do_not_count() -> None:
    results = [
        _result("database", DiagStatus.ok, "ok"),
        _result("backups", DiagStatus.warn, "backups_disabled"),
        _result("runners", DiagStatus.warn, "no_runners"),
    ]
    assert overall(results) is DiagStatus.warn
    assert overall(results, {"backups"}) is DiagStatus.warn
    assert overall(results, {"backups", "runners"}) is DiagStatus.ok
    assert overall([_result("disk", DiagStatus.fail, "disk_critical")], {"backups"}) is DiagStatus.fail
