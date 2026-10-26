"""Сессия конфликтов: стороны слияния, файлы с конфликтами и файлы, которые слились сами, черновики решений."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.git_sync.entities import CommitBrief
from hse_doc_studio.core.git_sync.merge.choices import FileChoice, FileResolution
from hse_doc_studio.core.git_sync.merge.drafts import progress, prune_all
from hse_doc_studio.core.git_sync.merge.entities import MergeAction, MergeOp
from hse_doc_studio.core.git_sync.merge.signature_groups import group_paths
from hse_doc_studio.core.git_sync.protocols import IGitRepoReader
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.template_update.errors import TemplateVersionUnavailableError
from hse_doc_studio.core.template_update.layout import doc_resolver
from hse_doc_studio.use_cases.git_sync.conflict_support import ConflictSessions, LoadedSession
from hse_doc_studio.use_cases.git_sync.conflict_views import (
    ConflictFileView,
    ConflictSessionView,
    FileSide,
    FileSides,
    SessionCounts,
    SessionSide,
)
from hse_doc_studio.use_cases.template_update.planning import current_version

# Сколько файлов, слившихся без участия человека, перечисляется: остальные видны только числом.
MAX_LISTED_AUTO = 200
_CHOICE_ORDER = (FileChoice.mine, FileChoice.theirs, FileChoice.newest)


@dataclass
class GetConflictsInput:
    project_id: UUID


class Briefs:
    """Кто и когда сделал коммит; один коммит читается один раз."""

    def __init__(self, reader: IGitRepoReader, folder: Path) -> None:
        self._reader = reader
        self._folder = folder
        self._seen: dict[str, CommitBrief | None] = {}

    def get(self, sha: str | None) -> CommitBrief | None:
        if sha is None:
            return None
        if sha not in self._seen:
            found = self._reader.commit_briefs(self._folder, sha, limit=1)
            self._seen[sha] = found[0] if found else None
        return self._seen[sha]

    def side(self, sha: str | None) -> SessionSide | None:
        if sha is None:
            return None
        brief = self.get(sha)
        if brief is None:
            return SessionSide(sha, None, None, None)
        return SessionSide(sha, brief.author, brief.created_at, brief.message)


def file_sides(reader: IGitRepoReader, loaded: LoadedSession, op: MergeOp, briefs: Briefs) -> FileSides:
    """Файл у каждой стороны; автор и время известны только у тех, что правили путь после общей базы."""
    folder, base = loaded.project.folder, loaded.plan.base_commit

    def side(content: bytes | None, tip: str) -> FileSide:
        if content is None:
            return FileSide(False)
        stamp = reader.path_stamp(folder, tip, op.path, exclude_reachable_from=base)
        brief = briefs.get(stamp.sha) if stamp else None
        return FileSide(True, len(content), brief.author if brief else None, stamp.committed_at if stamp else None)

    return FileSides(
        ours=side(op.ours, loaded.ours),
        theirs=side(op.theirs, loaded.theirs),
        base=FileSide(op.base is not None, len(op.base) if op.base is not None else None),
    )


class GetConflictsUC:
    def __init__(
        self, *, sessions: ConflictSessions, reader: IGitRepoReader, template_repo: ITemplateRepository
    ) -> None:
        self._sessions = sessions
        self._reader = reader
        self._templates = template_repo

    async def execute(self, inp: GetConflictsInput) -> ConflictSessionView:
        loaded = await self._sessions.load(inp.project_id)
        return await asyncio.to_thread(self._build, loaded)

    def _doc_of(self, project: Project) -> Callable[[str], str | None]:
        try:
            return doc_resolver(project, current_version(self._templates, project))
        except TemplateVersionUnavailableError:
            return lambda _path: None

    def _build(self, loaded: LoadedSession) -> ConflictSessionView:
        plan, folder = loaded.plan, loaded.project.folder
        hidden = group_paths(plan)
        drafts = prune_all({op.path: op for op in plan.ops}, loaded.pending.drafts)
        doc_of = self._doc_of(loaded.project)
        briefs = Briefs(self._reader, folder)
        shown = [op for op in plan.ops if op.path not in hidden]
        conflicts = [op for op in shown if op.needs_decision]
        auto = [op for op in shown if not op.needs_decision]
        files = [
            self._file(loaded, op, drafts, doc_of, briefs, detailed=op.needs_decision or _is_newest(op))
            for op in [*conflicts, *auto[:MAX_LISTED_AUTO]]
        ]
        unresolved = sum(not item.resolved for item in files if item.action == MergeAction.conflict.value)
        return ConflictSessionView(
            id=loaded.pending.session_id,
            fingerprint=plan.fingerprint,
            ours=briefs.side(loaded.ours) or SessionSide(loaded.ours, None, None, None),
            theirs=briefs.side(loaded.theirs) or SessionSide(loaded.theirs, None, None, None),
            base=briefs.side(plan.base_commit),
            counts=SessionCounts(conflict=len(conflicts), auto=len(auto), total=len(shown)),
            unresolved=unresolved,
            drafts_saved_at=loaded.pending.drafts_saved_at,
            warnings=plan.warnings,
            files=tuple(files),
        )

    def _file(
        self,
        loaded: LoadedSession,
        op: MergeOp,
        drafts: Mapping[str, FileResolution],
        doc_of: Callable[[str], str | None],
        briefs: Briefs,
        *,
        detailed: bool,
    ) -> ConflictFileView:
        resolution = drafts.get(op.path)
        done = progress(op, resolution)
        sides = (
            file_sides(self._reader, loaded, op, briefs)
            if detailed
            else FileSides(
                ours=_plain(op.ours),
                theirs=_plain(op.theirs),
                base=_plain(op.base),
            )
        )
        return ConflictFileView(
            path=op.path,
            owner=None,
            kind=op.kind.value,
            action=op.action.value,
            conflict_type=op.conflict_type.value if op.conflict_type else None,
            hunks=len(op.hunks),
            open_hunks=done.open_hunks,
            fields=len(op.fields) if op.needs_decision else len(op.auto),
            open_fields=done.open_fields,
            resolved=done.resolved,
            resolution=resolution,
            allowed=tuple(c.value for c in _CHOICE_ORDER if c in op.allowed_choices()),
            default_resolution=op.default_choice.value if op.default_choice else None,
            sides=sides,
            copy_path=op.copy_path,
            doc_id=doc_of(op.path),
        )


def _is_newest(op: MergeOp) -> bool:
    return op.action is MergeAction.binary_newest


def _plain(content: bytes | None) -> FileSide:
    return FileSide(content is not None, None if content is None else len(content))
