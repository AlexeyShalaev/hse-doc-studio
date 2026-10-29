"""Настройки синхронизации одного проекта: фоновая выборка и подтверждение предупреждения об общей папке."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import SyncState
from hse_doc_studio.core.git_sync.policy import MIN_FETCH_INTERVAL_S
from hse_doc_studio.core.git_sync.protocols import IGitStoreRemotes, IGitSyncStateRepository
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.use_cases.git_sync.status import GitStatusBuilder, GitStatusView, default_state
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class UpdateGitSettingsInput:
    project_id: UUID
    auto_fetch: bool | None = None
    # `interval_given` отличает «период не трогать» от «вернуть общую настройку» (interval_s=None).
    interval_given: bool = False
    interval_s: int | None = None
    shared_folder_ack: bool | None = None


class UpdateGitSettingsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        status_builder: GitStatusBuilder,
    ) -> None:
        self._get_project = GetProjectUC(project_repo, project_index_repo)
        self._remotes = store_remotes
        self._states = state_repo
        self._status = status_builder

    async def execute(self, inp: UpdateGitSettingsInput) -> GitStatusView:
        project = (await self._get_project.execute(GetProjectInput(project_id=inp.project_id))).project
        if inp.interval_given and inp.interval_s is not None and inp.interval_s < MIN_FETCH_INTERVAL_S:
            raise ValueError(f"interval_s must be at least {MIN_FETCH_INTERVAL_S} seconds")
        await asyncio.to_thread(self._apply, project, inp)
        return await self._status.view(project)

    def _apply(self, project: Project, inp: UpdateGitSettingsInput) -> None:
        config = self._remotes.read(project)
        if config is None:
            raise NotFoundError(localized_error("Удалённый репозиторий не подключён", "No remote is connected"))
        state = self._states.get(project.folder) or default_state(config, None)
        self._states.save(project.folder, self._changed(state, inp))

    @staticmethod
    def _changed(state: SyncState, inp: UpdateGitSettingsInput) -> SyncState:
        if inp.auto_fetch is not None:
            state = replace(state, auto_fetch=inp.auto_fetch)
        if inp.interval_given:
            state = replace(state, fetch_interval_s=inp.interval_s)
        if inp.shared_folder_ack is not None:
            state = replace(state, shared_folder_ack=inp.shared_folder_ack)
        return state
