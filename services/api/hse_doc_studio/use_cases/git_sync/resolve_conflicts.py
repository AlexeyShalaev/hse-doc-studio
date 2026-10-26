"""Применение решений по конфликтам: проверки сразу, слияние и отправка фоновой операцией.

Всё, что можно сказать человеку немедленно (план устарел, решены не все конфликты, в тексте остались маркеры),
приходит ответом на запрос. Сама запись слияния и отправка идут в операции `resolve`, как обычная синхронизация.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.git_sync.entities import OperationKind
from hse_doc_studio.core.git_sync.merge.choices import FileResolution
from hse_doc_studio.core.git_sync.merge.drafts import prune_all
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.use_cases.git_sync.conflict_support import ConflictSessions
from hse_doc_studio.use_cases.git_sync.start_sync import StartSyncOutput, StartSyncUC
from hse_doc_studio.use_cases.git_sync.sync_apply import ResolveRequest, SyncApplier
from hse_doc_studio.use_cases.git_sync.sync_project import SyncProjectUC


@dataclass
class ResolveConflictsInput:
    project_id: UUID
    fingerprint: str
    # None: взять сохранённые черновики.
    resolutions: Mapping[str, FileResolution] | None
    push: bool


class ResolveConflictsUC:
    def __init__(
        self,
        *,
        sessions: ConflictSessions,
        start: StartSyncUC,
        applier: SyncApplier,
        sync: SyncProjectUC,
        operations: IGitOperationRegistry,
        locks: IVcsFolderLocks,
    ) -> None:
        self._sessions = sessions
        self._start = start
        self._applier = applier
        self._sync = sync
        self._operations = operations
        self._locks = locks

    async def execute(self, inp: ResolveConflictsInput) -> StartSyncOutput:
        project = await self._sessions.project(inp.project_id)
        await asyncio.to_thread(self._start.preflight, project)
        loaded = await asyncio.to_thread(self._sessions.load_for, project)
        if inp.resolutions is not None:
            resolutions = dict(inp.resolutions)
        else:
            resolutions = prune_all({op.path: op for op in loaded.plan.ops}, loaded.pending.drafts)
        request = ResolveRequest(inp.fingerprint, resolutions, inp.push)
        async with self._locks.for_folder(project.folder):
            await asyncio.to_thread(self._applier.check_resolution, project, loaded.state, request)
        operation = self._operations.begin(OperationKind.resolve, project_id=project.id, folder=project.folder)
        task = asyncio.create_task(self._sync.run(project, operation.id, request), name=f"git-resolve-{operation.id}")
        self._operations.attach_task(operation.id, task)
        return StartSyncOutput(operation_id=operation.id)
