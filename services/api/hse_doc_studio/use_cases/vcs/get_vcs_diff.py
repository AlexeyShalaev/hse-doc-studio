from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.entities import VcsDiff
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC


@dataclass
class GetVcsDiffInput:
    project_id: UUID
    from_id: str | None = None
    to_id: str | None = None
    path: str | None = None
    max_bytes: int | None = None


@dataclass
class GetVcsDiffOutput:
    diff: VcsDiff


class GetVcsDiffUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> None:
        self._vcs = vcs_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetVcsDiffInput) -> GetVcsDiffOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        diff = await asyncio.to_thread(
            lambda: self._vcs.diff(
                project,
                from_id=inp.from_id,
                to_id=inp.to_id,
                path=inp.path,
                max_bytes=inp.max_bytes,
            )
        )
        return GetVcsDiffOutput(diff=diff)
