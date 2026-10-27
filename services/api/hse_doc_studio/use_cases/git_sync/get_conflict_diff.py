"""Дифф одного файла сессии конфликтов: что изменила каждая сторона и что получится при текущем черновике."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.git_sync.merge.entities import ContentKind, MergeOp
from hse_doc_studio.core.git_sync.merge.preview import preview_result
from hse_doc_studio.core.git_sync.protocols import IFieldResolver
from hse_doc_studio.core.template_update.text import is_binary, unified_diff
from hse_doc_studio.use_cases.git_sync.conflict_support import ConflictSessions, LoadedSession
from hse_doc_studio.use_cases.git_sync.conflict_views import ConflictDiff


class ConflictDiffView(StrEnum):
    ours = "ours"  # что изменила моя сторона: база → моё
    theirs = "theirs"  # что изменила чужая сторона: база → чужое
    result = "result"  # что получится: моё → итог по черновику


@dataclass
class GetConflictDiffInput:
    project_id: UUID
    path: str
    view: ConflictDiffView


class GetConflictDiffUC:
    def __init__(self, *, sessions: ConflictSessions, resolver: IFieldResolver) -> None:
        self._sessions = sessions
        self._resolver = resolver

    async def execute(self, inp: GetConflictDiffInput) -> ConflictDiff:
        loaded = await self._sessions.load(inp.project_id)
        return await asyncio.to_thread(self._diff, loaded, loaded.op(inp.path), inp.view)

    def _diff(self, loaded: LoadedSession, op: MergeOp, view: ConflictDiffView) -> ConflictDiff:
        if op.kind is ContentKind.binary or is_binary(op.path, op.base, op.ours, op.theirs):
            return ConflictDiff(path=op.path, binary=True, patch="", truncated=False)
        if view is ConflictDiffView.ours:
            patch, truncated = unified_diff(op.path, op.base, op.ours, "base", "mine")
        elif view is ConflictDiffView.theirs:
            patch, truncated = unified_diff(op.path, op.base, op.theirs, "base", "theirs")
        else:
            draft = loaded.pending.drafts.get(op.path)
            patch, truncated = unified_diff(
                op.path, op.ours, preview_result(op, draft, self._resolver), "mine", "result"
            )
        return ConflictDiff(path=op.path, binary=False, patch=patch, truncated=truncated)
