from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.constants import DEFAULT_VCS_EXCLUDE
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class EnsureVcsInput:
    project_id: UUID


@dataclass
class EnsureVcsOutput:
    available: bool
    initialized: bool


class EnsureVcsUC:
    """Idempotently make sure a project has its VCS store. No-op if it exists;
    reports unavailable (without raising) when the project folder isn't reachable.
    """

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        vcs_service: IVcsService,
    ) -> None:
        self._vcs = vcs_service
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: EnsureVcsInput) -> EnsureVcsOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if not self._vcs.is_available(project):
            return EnsureVcsOutput(available=False, initialized=False)
        if not self._vcs.is_initialized(project):
            await asyncio.to_thread(self._vcs.init, project, list(DEFAULT_VCS_EXCLUDE))
        else:
            # Refresh the ignore policy for an existing store (e.g. after an update
            # tightened what gets versioned).
            await asyncio.to_thread(self._vcs.write_ignore, project, list(DEFAULT_VCS_EXCLUDE))
        return EnsureVcsOutput(available=True, initialized=self._vcs.is_initialized(project))
