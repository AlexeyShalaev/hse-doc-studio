"""Черновик решений: человек отмечает выбор по участкам и полям, не применяя его."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from hse_doc_studio.core.git_sync.error_messages import git_error, resolution_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.merge.choices import FileResolution
from hse_doc_studio.core.git_sync.merge.drafts import is_empty, progress, prune, prune_all
from hse_doc_studio.core.git_sync.protocols import IGitSyncStateRepository
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.use_cases.git_sync.conflict_support import ConflictSessions, LoadedSession


@dataclass
class SaveDraftInput:
    project_id: UUID
    resolutions: Mapping[str, FileResolution]


class SaveDraftUC:
    """Решения по пути заменяют прежние целиком; пустое решение снимает черновик с пути."""

    def __init__(
        self, *, sessions: ConflictSessions, state_repo: IGitSyncStateRepository, locks: IVcsFolderLocks
    ) -> None:
        self._sessions = sessions
        self._states = state_repo
        self._locks = locks

    async def execute(self, inp: SaveDraftInput) -> None:
        loaded = await self._sessions.load(inp.project_id)
        self._validate(loaded, inp.resolutions)
        async with self._locks.for_folder(loaded.project.folder):
            await asyncio.to_thread(self._save, loaded, inp.resolutions)

    @staticmethod
    def _validate(loaded: LoadedSession, resolutions: Mapping[str, FileResolution]) -> None:
        for path, resolution in resolutions.items():
            op = loaded.plan.op(path)
            if op is None or (not is_empty(resolution) and prune(op, resolution) != resolution):
                raise resolution_error(GitErrorCode.invalid_resolution, path)

    def _save(self, loaded: LoadedSession, resolutions: Mapping[str, FileResolution]) -> None:
        folder = loaded.project.folder
        state = self._states.get(folder)
        pending = state.pending if state is not None else None
        if state is None or pending is None or pending.session_id != loaded.pending.session_id:
            raise git_error(GitErrorCode.no_conflicts)
        ops = {op.path: op for op in loaded.plan.ops}
        drafts = prune_all(ops, pending.drafts)
        for path, resolution in resolutions.items():
            if is_empty(resolution):
                drafts.pop(path, None)
            else:
                drafts[path] = resolution
        left = sum(not progress(op, drafts.get(op.path)).resolved for op in loaded.plan.conflicts)
        updated = replace(
            pending,
            files_total=len(loaded.plan.conflicts),
            files_open=left,
            ours=loaded.ours,
            theirs=loaded.theirs,
            base=loaded.plan.base_commit,
            fingerprint=loaded.plan.fingerprint,
            drafts=drafts,
            drafts_saved_at=datetime.now(UTC),
        )
        self._states.save(folder, replace(state, pending=updated))
