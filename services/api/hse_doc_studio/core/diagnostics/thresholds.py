"""Пороги самодиагностики в `instance_settings` (ключи `diagnostics.*`). Испорченное значение читается как умолчание.

Пороги места на диске общие с контролем места (`storage.warn_percent`, `storage.critical_percent`), здесь их нет.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields

KEY_PREFIX = "diagnostics."
KEY_LAST_TICK = KEY_PREFIX + "last_tick_at"
KEY_NOTIFY = KEY_PREFIX + "notify"


@dataclass(frozen=True)
class DiagThresholds:
    db_latency_warn_ms: int = 300
    db_latency_fail_ms: int = 2000
    store_latency_warn_ms: int = 2000
    store_latency_fail_ms: int = 15000
    queue_wait_warn_s: int = 600
    queue_wait_fail_s: int = 3600
    stuck_job_warn_s: int = 300
    stuck_job_fail_s: int = 1800
    tls_warn_days: int = 21
    tls_fail_days: int = 7
    backup_warn_hours: int = 36
    backup_fail_hours: int = 96
    # Антидребезг уведомлений: сколько проверок подряд статус должен продержаться и как часто напоминать.
    confirm_runs: int = 2
    repeat_hours: int = 24
    notify: bool = True


BOUNDS: dict[str, tuple[int, int]] = {
    "db_latency_warn_ms": (10, 60_000),
    "db_latency_fail_ms": (20, 120_000),
    "store_latency_warn_ms": (100, 120_000),
    "store_latency_fail_ms": (200, 300_000),
    "queue_wait_warn_s": (30, 86_400),
    "queue_wait_fail_s": (60, 604_800),
    "stuck_job_warn_s": (30, 86_400),
    "stuck_job_fail_s": (60, 604_800),
    "tls_warn_days": (2, 120),
    "tls_fail_days": (1, 60),
    "backup_warn_hours": (1, 720),
    "backup_fail_hours": (2, 2160),
    "confirm_runs": (1, 10),
    "repeat_hours": (1, 168),
}
# Пары «предупреждение, сбой»: сбой наступает строго позже (для TLS строго раньше по числу дней до конца срока).
PAIRS: tuple[tuple[str, str], ...] = (
    ("db_latency_warn_ms", "db_latency_fail_ms"),
    ("store_latency_warn_ms", "store_latency_fail_ms"),
    ("queue_wait_warn_s", "queue_wait_fail_s"),
    ("stuck_job_warn_s", "stuck_job_fail_s"),
    ("backup_warn_hours", "backup_fail_hours"),
)
TLS_PAIR = ("tls_warn_days", "tls_fail_days")
DEFAULTS = DiagThresholds()


def _int(raw: object, name: str) -> int | None:
    lo, hi = BOUNDS[name]
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and lo <= raw <= hi else None


def misordered(values: Mapping[str, int]) -> list[tuple[str, str]]:
    """Пары, нарушившие порядок: предупреждение раньше сбоя (для TLS наоборот: предупреждают за большее число дней)."""
    bad = [(warn, fail) for warn, fail in PAIRS if values[warn] >= values[fail]]
    if values[TLS_PAIR[0]] <= values[TLS_PAIR[1]]:
        bad.append(TLS_PAIR)
    return bad


def thresholds_from(stored: Mapping[str, object]) -> DiagThresholds:
    """Правка админа в границах; пара, нарушившая порядок, целиком возвращается к умолчанию."""
    values: dict[str, int] = {}
    for name in BOUNDS:
        picked = _int(stored.get(KEY_PREFIX + name), name)
        values[name] = picked if picked is not None else int(getattr(DEFAULTS, name))
    for pair in misordered(values):
        for name in pair:
            values[name] = int(getattr(DEFAULTS, name))
    notify = stored.get(KEY_NOTIFY)
    return DiagThresholds(**values, notify=notify if isinstance(notify, bool) else DEFAULTS.notify)


def threshold_names() -> list[str]:
    return [f.name for f in fields(DiagThresholds) if f.name != "notify"]
