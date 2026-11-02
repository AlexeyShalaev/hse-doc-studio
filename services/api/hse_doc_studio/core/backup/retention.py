"""Политика хранения: какие успешные бэкапы пора удалить. Чистая функция."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from hse_doc_studio.core.backup.entities import BackupRun, RunStatus


def select_expired(runs: Sequence[BackupRun], *, keep_last: int, keep_days: int, now: datetime) -> list[BackupRun]:
    """Успешные неудалённые запуски одного назначения, которые подлежат удалению.

    Самые новые `keep_last` остаются всегда; из остальных уходят старше `keep_days` суток. Ноль отключает правило
    (оба нуля хранят всё). Самый новый успешный бэкап не удаляется никогда, даже если он старше срока.
    """
    alive = sorted(
        (run for run in runs if run.status is RunStatus.ok and run.removed_at is None and run.backup_id),
        key=lambda run: run.started_at,
        reverse=True,
    )
    if not alive or (keep_last <= 0 and keep_days <= 0):
        return []
    expired: list[BackupRun] = []
    for position, run in enumerate(alive):
        if position == 0:
            continue
        beyond_count = keep_last > 0 and position >= keep_last
        too_old = keep_days > 0 and run.started_at < now - timedelta(days=keep_days)
        if keep_last > 0 and keep_days > 0:
            drop = beyond_count and too_old
        elif keep_last > 0:
            drop = beyond_count
        else:
            drop = too_old
        if drop:
            expired.append(run)
    return expired
