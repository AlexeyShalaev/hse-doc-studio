"""Состояние проверки между проходами и антидребезг уведомлений.

Статус должен продержаться `confirm_runs` проходов подряд, прежде чем админы получат уведомление; повтор о той же
проблеме не чаще `repeat`. Возвращение в ok сообщается, только если о проблеме уже сообщали и ok устоялся.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from hse_doc_studio.core.diagnostics.entities import CheckResult, DiagStatus

NOTICE_FAIL = "diag_fail"
NOTICE_WARN = "diag_warn"
NOTICE_RECOVERED = "diag_recovered"


@dataclass(frozen=True)
class CheckState:
    result: CheckResult
    status_since: datetime
    streak: int = 1
    notified_status: DiagStatus | None = None
    notified_at: datetime | None = None


def advance(
    prev: CheckState | None,
    result: CheckResult,
    *,
    confirm_runs: int,
    repeat: timedelta,
    now: datetime,
) -> tuple[CheckState, str | None]:
    """Новое состояние и вид уведомления (None: молчим)."""
    same = prev is not None and prev.result.status is result.status
    state = CheckState(
        result=result,
        status_since=prev.status_since if prev is not None and same else result.checked_at,
        streak=prev.streak + 1 if prev is not None and same else 1,
        notified_status=prev.notified_status if prev else None,
        notified_at=prev.notified_at if prev else None,
    )
    if state.streak < confirm_runs:
        return state, None
    if result.status is DiagStatus.ok:
        if state.notified_status is None:
            return state, None
        return replace(state, notified_status=None, notified_at=now), NOTICE_RECOVERED
    changed = state.notified_status is not result.status
    due = state.notified_at is not None and now - state.notified_at >= repeat
    if not (changed or due):
        return state, None
    notice = NOTICE_FAIL if result.status is DiagStatus.fail else NOTICE_WARN
    return replace(state, notified_status=result.status, notified_at=now), notice
