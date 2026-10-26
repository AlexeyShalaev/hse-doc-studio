"""Общее для сценариев экрана конфликтов: открытая сессия и её план, пересобранный из объектов хранилища."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import PendingSession, SyncState
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.merge.entities import MergeOp, MergePlan
from hse_doc_studio.core.git_sync.protocols import IGitRepoReader, IGitSyncStateRepository
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.git_sync.conflict_plan import ConflictPlanner
from hse_doc_studio.use_cases.git_sync.sync_apply import HEADS_PREFIX, TRACKING_PREFIX
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass(frozen=True)
class LoadedSession:
    project: Project
    state: SyncState
    pending: PendingSession
    plan: MergePlan
    ours: str
    theirs: str

    def op(self, path: str) -> MergeOp:
        found = self.plan.op(path)
        if found is None:
            raise NotFoundError(localized_error(f"Файла {path} нет в слиянии", f"{path} is not part of the merge"))
        return found


class ConflictSessions:
    """Открытая сессия конфликтов проекта.

    Сессия живёт в hse-sync.json как напоминание «слияние остановлено». Сами конфликты каждый раз считаются заново
    по текущему коммиту ветки и последней известной вершине чужой: правки, сделанные за это время, видны сразу,
    а отпечаток плана говорит, изменилось ли то, что решает человек.
    """

    def __init__(
        self,
        *,
        get_project: GetProjectUC,
        state_repo: IGitSyncStateRepository,
        reader: IGitRepoReader,
        planner: ConflictPlanner,
    ) -> None:
        self._get_project = get_project
        self._states = state_repo
        self._reader = reader
        self._planner = planner

    async def project(self, project_id: UUID) -> Project:
        return (await self._get_project.execute(GetProjectInput(project_id=project_id))).project

    async def load(self, project_id: UUID) -> LoadedSession:
        return await asyncio.to_thread(self.load_for, await self.project(project_id))

    def load_for(self, project: Project) -> LoadedSession:
        """Бросает no_conflicts, если слияние не стоит или конфликтов уже нет."""
        folder = project.folder
        state = self._states.get(folder)
        if state is None or state.pending is None:
            raise git_error(GitErrorCode.no_conflicts)
        ours = self._reader.rev_parse(folder, f"{HEADS_PREFIX}{state.local_branch}")
        theirs = self._reader.rev_parse(folder, f"{TRACKING_PREFIX}{state.remote_branch}")
        if ours is None or theirs is None or ours == theirs or self._reader.is_ancestor(folder, theirs, ours):
            raise git_error(GitErrorCode.no_conflicts)
        plan = self._planner.plan(folder, ours, theirs, adopted_unrelated=state.adopted_unrelated)
        if plan.is_clean:
            raise git_error(GitErrorCode.no_conflicts)
        return LoadedSession(project, state, state.pending, plan, ours, theirs)
