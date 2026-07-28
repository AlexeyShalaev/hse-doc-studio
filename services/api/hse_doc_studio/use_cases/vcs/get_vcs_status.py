from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsSettings, VcsStatus
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class GetVcsStatusInput:
    project_id: UUID


@dataclass
class GetVcsStatusOutput:
    status: VcsStatus


class GetVcsStatusUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> None:
        self._vcs = vcs_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetVcsStatusInput) -> GetVcsStatusOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        settings = VcsSettings.from_meta(project.meta)
        status = await asyncio.to_thread(self._vcs.status, project, settings)
        return GetVcsStatusOutput(status=status)
