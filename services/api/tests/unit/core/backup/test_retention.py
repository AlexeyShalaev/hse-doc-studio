from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hse_doc_studio.core.backup.entities import BackupRun, RunStatus, RunTrigger
from hse_doc_studio.core.backup.retention import select_expired

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _run(index: int, age_days: float, status: RunStatus = RunStatus.ok, removed: bool = False) -> BackupRun:
    started = NOW - timedelta(days=age_days)
    return BackupRun(
        id=f"r{index}",
        destination_id="d",
        destination_name="d",
        trigger=RunTrigger.schedule,
        status=status,
        stage=None,
        started_at=started,
        finished_at=started + timedelta(minutes=1),
        backup_id=f"20261001T000000Z-00000{index}",
        removed_at=NOW if removed else None,
    )


def _ids(runs: list[BackupRun]) -> set[str]:
    return {run.id for run in runs}


def test__keep_last_only__drops_older_beyond_count() -> None:
    runs = [_run(i, i) for i in range(1, 8)]
    assert _ids(select_expired(runs, keep_last=3, keep_days=0, now=NOW)) == {"r4", "r5", "r6", "r7"}


def test__keep_days_only__drops_older_than_limit_but_never_the_newest() -> None:
    runs = [_run(1, 40), _run(2, 50)]
    assert _ids(select_expired(runs, keep_last=0, keep_days=30, now=NOW)) == {"r2"}


def test__both__needs_beyond_count_and_older_than_days() -> None:
    runs = [_run(1, 1), _run(2, 2), _run(3, 3), _run(4, 40), _run(5, 50)]
    # последние 2 остаются всегда; из остальных уходят только старше 30 суток
    assert _ids(select_expired(runs, keep_last=2, keep_days=30, now=NOW)) == {"r4", "r5"}


def test__both_zero__keeps_everything() -> None:
    runs = [_run(i, 100 * i) for i in range(1, 5)]
    assert select_expired(runs, keep_last=0, keep_days=0, now=NOW) == []


def test__failed_and_removed_runs_are_ignored() -> None:
    runs = [_run(1, 1), _run(2, 2, status=RunStatus.failed), _run(3, 3, removed=True), _run(4, 4)]
    assert _ids(select_expired(runs, keep_last=1, keep_days=0, now=NOW)) == {"r4"}


def test__newest_successful_backup_survives_even_when_expired() -> None:
    runs = [_run(1, 400)]
    assert select_expired(runs, keep_last=1, keep_days=30, now=NOW) == []
