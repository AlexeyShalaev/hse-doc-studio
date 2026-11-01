"""Фейки автообновления: запуски в памяти, фид, «бэкап» и транспорт апдейтера прямо в сервис."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from hse_doc_studio.core.backup.entities import BackupRun
from hse_doc_studio.core.backup.entities import RunStatus as BackupStatus
from hse_doc_studio.core.backup.entities import RunTrigger as BackupTrigger
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.core.server_update.entities import ACTIVE_STATUSES, RunKind, RunStatus, UpdateRun
from hse_doc_studio.core.server_update.protocols import FeedAnswer


class InMemoryUpdateRuns:
    def __init__(self) -> None:
        self.items: dict[str, UpdateRun] = {}

    async def add(self, run: UpdateRun) -> bool:
        if any(r.status in ACTIVE_STATUSES for r in self.items.values()):
            return False
        self.items[run.id] = run
        return True

    async def get(self, run_id: str) -> UpdateRun | None:
        return self.items.get(run_id)

    async def lock(self, run_id: str) -> UpdateRun | None:
        return self.items.get(run_id)

    async def save(self, run: UpdateRun) -> None:
        self.items[run.id] = run

    async def active(self) -> UpdateRun | None:
        return next((r for r in self.items.values() if r.status in ACTIVE_STATUSES), None)

    async def claim_next(self, *, now_iso: str) -> UpdateRun | None:
        queued = sorted((r for r in self.items.values() if r.status is RunStatus.queued), key=lambda r: r.created_at)
        if not queued:
            return None
        run = replace(
            queued[0], status=RunStatus.running, started_at=datetime.fromisoformat(now_iso), phase="preflight"
        )
        self.items[run.id] = run
        return run

    async def page(self, window: Window) -> Found[UpdateRun]:
        ordered = sorted(self.items.values(), key=lambda r: r.created_at, reverse=True)
        return Found(ordered[window.offset : window.offset + window.limit], len(ordered))

    async def last_finished(self) -> UpdateRun | None:
        done = [r for r in self.items.values() if r.status not in ACTIVE_STATUSES]
        return max(done, key=lambda r: r.created_at) if done else None

    async def last_succeeded_update(self) -> UpdateRun | None:
        ok = [r for r in self.items.values() if r.status is RunStatus.succeeded and r.kind is RunKind.update]
        return max(ok, key=lambda r: r.created_at) if ok else None

    async def failed_targets(self) -> frozenset[str]:
        failed = {
            r.to_version
            for r in self.items.values()
            if r.kind is RunKind.update and r.status in {RunStatus.rolled_back, RunStatus.failed}
        }
        undone = {
            r.from_version
            for r in self.items.values()
            if r.kind is RunKind.rollback and r.status is RunStatus.succeeded
        }
        return frozenset(failed | undone)

    async def counts(self) -> dict[RunStatus, int]:
        out: dict[RunStatus, int] = {}
        for r in self.items.values():
            out[r.status] = out.get(r.status, 0) + 1
        return out

    async def recent(self, limit: int) -> list[UpdateRun]:
        return sorted(self.items.values(), key=lambda r: r.created_at, reverse=True)[:limit]


class StaticSource:
    def __init__(self, answer: FeedAnswer) -> None:
        self.answer = answer
        self.calls = 0

    async def fetch(self) -> FeedAnswer:
        self.calls += 1
        return self.answer


class FakeBackupStarter:
    """Заменяет BackupService: запись о запуске кладёт в общий `InMemoryRuns`, исход выставляет тест."""

    def __init__(self, runs: Any, *, error: BackupErrorCode | None = None) -> None:
        self.runs = runs
        self.error = error
        self.started = 0

    async def start(self, *, trigger: BackupTrigger, destination_id: str | None, actor_id: str | None) -> BackupRun:
        if self.error is not None:
            raise BackupError(self.error, "fake")
        self.started += 1
        run = BackupRun(
            id=f"00000000-0000-0000-0000-{self.started:012d}",
            destination_id=None,
            destination_name="disk",
            trigger=trigger,
            status=BackupStatus.running,
            stage="starting",
            started_at=datetime(2026, 11, 1, tzinfo=None).astimezone(),
            started_by=actor_id,
        )
        await self.runs.start(run)
        return run

    async def finish(self, run_id: str, status: BackupStatus, error: str | None = None) -> None:
        await self.runs.finish(
            run_id,
            status=status,
            at=datetime.now().astimezone(),
            size_bytes=1,
            backup_id="b1",
            error=error,
            manifest_sha256=None,
        )
