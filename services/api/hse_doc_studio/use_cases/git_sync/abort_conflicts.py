"""Отказ от слияния: сессия конфликтов снимается, файлы проекта остаются как были."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.protocols import IGitMergeCommitter, IGitOperationRegistry, IGitSyncStateRepository
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.use_cases.git_sync.conflict_support import ConflictSessions
from hse_doc_studio.use_cases.git_sync.status import GetGitStatusInput, GetGitStatusUC, GitStatusView


@dataclass
class AbortConflictsInput:
    project_id: UUID


class AbortConflictsUC:
    """Повторный отказ не ошибка: после него проект и так без открытых конфликтов."""

    def __init__(
        self,
        *,
        sessions: ConflictSessions,
        state_repo: IGitSyncStateRepository,
        committer: IGitMergeCommitter,
        operations: IGitOperationRegistry,
        locks: IVcsFolderLocks,
        status: GetGitStatusUC,
    ) -> None:
        self._sessions = sessions
        self._states = state_repo
        self._committer = committer
        self._operations = operations
        self._locks = locks
        self._status = status

    async def execute(self, inp: AbortConflictsInput) -> GitStatusView:
        project = await self._sessions.project(inp.project_id)
        async with self._locks.for_folder(project.folder):
            if self._operations.is_busy(project.folder):
                raise git_error(GitErrorCode.sync_busy)
            await asyncio.to_thread(self._clear, project.folder)
        return await self._status.execute(GetGitStatusInput(project_id=inp.project_id))

    def _clear(self, folder: Path) -> None:
        state = self._states.get(folder)
        if state is not None and state.pending is not None:
            self._states.save(folder, replace(state, pending=None))
            if state.pending.theirs_ref is not None:
                # Ветка из файла нужна была только этому слиянию.
                self._committer.delete_ref(folder, state.pending.theirs_ref)
