from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsCommitDetail
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class GetVcsCommitInput:
    project_id: UUID
    commit_id: str


@dataclass
class GetVcsCommitOutput:
    detail: VcsCommitDetail


class GetVcsCommitUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> None:
        self._vcs = vcs_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetVcsCommitInput) -> GetVcsCommitOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        detail = await asyncio.to_thread(self._vcs.commit_detail, project, inp.commit_id)
        return GetVcsCommitOutput(detail=detail)
