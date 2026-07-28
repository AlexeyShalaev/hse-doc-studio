from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsSettings
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class GetVcsSettingsInput:
    project_id: UUID


@dataclass
class GetVcsSettingsOutput:
    settings: VcsSettings


class GetVcsSettingsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> None:
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetVcsSettingsInput) -> GetVcsSettingsOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        return GetVcsSettingsOutput(settings=VcsSettings.from_meta(project.meta))
