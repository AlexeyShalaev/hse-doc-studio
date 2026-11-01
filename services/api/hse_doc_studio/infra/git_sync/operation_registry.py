"""Реестр длительных операций Git-синхронизации в памяти процесса (порт IGitOperationRegistry).

Операция принадлежит папке проекта: пока она идёт, вторая на ту же папку не начнётся, а перенос и удаление
проекта откажутся. Итог остаётся доступным 15 минут, чтобы страница, которая опрашивает операцию, успела его
прочитать; долговременный итог лежит в hse-sync.json проекта. Реестр общий на процесс: после перезапуска
операций нет, а журнал применения слияния (`UpdateJournal`) разбирает запуск.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.git_sync.entities import (
    CloneResult,
    GitOperation,
    GitOperationError,
    OperationKind,
    OperationPhase,
    OperationStatus,
    SyncResult,
)
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode

KEEP_FINISHED = timedelta(minutes=15)


@dataclass
class _Entry:
    operation: GitOperation
    folder: Path | None
    task: asyncio.Task[object] | None = None


def _key(folder: Path) -> Path:
    return folder.resolve()


class InMemoryGitOperationRegistry:
    def __init__(
        self, *, keep_finished: timedelta = KEEP_FINISHED, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._keep = keep_finished
        self._now = clock or (lambda: datetime.now(UTC))
        self._entries: dict[str, _Entry] = {}
        self._lock = threading.RLock()

    def begin(self, kind: OperationKind, *, project_id: UUID | None, folder: Path | None) -> GitOperation:
        with self._lock:
            self._sweep()
            if folder is not None:
                running = self._running_for(folder)
                if running is not None:
                    raise git_error(GitErrorCode.sync_busy, operation_id=running.operation.id)
            actor = current_actor()
            operation = GitOperation(
                id=f"op_{uuid4().hex[:12]}",
                kind=kind,
                project_id=project_id,
                started_at=self._now(),
                owner=actor.key if actor is not None else None,
            )
            self._entries[operation.id] = _Entry(operation, folder)
            return replace(operation)

    def update(
        self,
        operation_id: str,
        *,
        phase: OperationPhase | None = None,
        percent: float | None = None,
        message: str | None = None,
        cancellable: bool | None = None,
    ) -> None:
        with self._lock:
            entry = self._entries.get(operation_id)
            if entry is None or entry.operation.status is not OperationStatus.running:
                return
            op = entry.operation
            if phase is not None and phase is not op.phase:
                # Новая фаза начинается без процента: прежний относился к предыдущей.
                op.phase = phase
                op.percent = None
            if percent is not None:
                # git печатает несколько этапов подряд (подсчёт, получение, дельты), и у каждого счёт идёт с нуля.
                op.percent = max(op.percent or 0.0, min(100.0, percent))
            if message is not None:
                op.message = message
            if cancellable is not None:
                op.cancellable = cancellable

    def finish(
        self,
        operation_id: str,
        *,
        status: OperationStatus = OperationStatus.succeeded,
        result: SyncResult | CloneResult | None = None,
        error: GitOperationError | None = None,
    ) -> None:
        with self._lock:
            entry = self._entries.get(operation_id)
            if entry is None or entry.operation.status is not OperationStatus.running:
                return
            op = entry.operation
            op.status = status
            op.result = result
            if isinstance(result, CloneResult):
                # Клонирование знает идентификатор проекта только в конце: до этого проекта у Студии не было.
                op.project_id = result.project_id
            op.error = error
            op.cancellable = False
            op.percent = None
            op.finished_at = self._now()
            entry.task = None

    def attach_task(self, operation_id: str, task: asyncio.Task[object]) -> None:
        with self._lock:
            entry = self._entries.get(operation_id)
            if entry is not None and entry.operation.status is OperationStatus.running:
                entry.task = task

    def cancel(self, operation_id: str) -> GitOperation | None:
        with self._lock:
            self._sweep()
            entry = self._entries.get(operation_id)
            if entry is None:
                return None
            op = entry.operation
            if op.status is not OperationStatus.running or not op.cancellable or entry.task is None:
                raise git_error(GitErrorCode.operation_not_cancellable)
            task = entry.task
        # Отмена задачи убивает дочерние процессы git; итог операции запишет сама задача в `finally`.
        task.cancel()
        return self.get(operation_id)

    def get(self, operation_id: str) -> GitOperation | None:
        with self._lock:
            self._sweep()
            entry = self._entries.get(operation_id)
            return None if entry is None else replace(entry.operation)

    def current_for(self, project_id: UUID) -> GitOperation | None:
        with self._lock:
            for entry in self._entries.values():
                op = entry.operation
                if op.project_id == project_id and op.status is OperationStatus.running:
                    return replace(op)
            return None

    def is_busy(self, folder: Path) -> bool:
        with self._lock:
            return self._running_for(folder) is not None

    def _running_for(self, folder: Path) -> _Entry | None:
        key = _key(folder)
        for entry in self._entries.values():
            if (
                entry.folder is not None
                and entry.operation.status is OperationStatus.running
                and _key(entry.folder) == key
            ):
                return entry
        return None

    def _sweep(self) -> None:
        horizon = self._now() - self._keep
        expired = [
            op_id
            for op_id, entry in self._entries.items()
            if entry.operation.finished_at is not None and entry.operation.finished_at < horizon
        ]
        for op_id in expired:
            del self._entries[op_id]
