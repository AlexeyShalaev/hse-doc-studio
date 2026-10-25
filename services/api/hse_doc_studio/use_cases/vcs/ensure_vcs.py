from __future__ import annotations

import asyncio
from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC
from hse_doc_studio.use_cases.vcs.excludes import project_vcs_exclude

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
        template_repo: ITemplateRepository | None = None,
    ) -> None:
        self._vcs = vcs_service
        self._template_repo = template_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: EnsureVcsInput) -> EnsureVcsOutput:
        project = (await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))).project
        if not self._vcs.is_available(project):
            return EnsureVcsOutput(available=False, initialized=False)
        exclude = project_vcs_exclude(project, self._template_repo)
        if not self._vcs.is_initialized(project):
            await asyncio.to_thread(self._vcs.init, project, exclude)
        else:
            # Refresh the ignore policy for an existing store (e.g. after an update
            # tightened what gets versioned).
            await asyncio.to_thread(self._vcs.write_ignore, project, exclude)
        return EnsureVcsOutput(available=True, initialized=self._vcs.is_initialized(project))
