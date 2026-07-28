from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class UnregisterProjectInput:
    project_id: UUID


class UnregisterProjectUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: UnregisterProjectInput) -> None:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        self._project_index_repo.unregister(project.folder)
        logger.info(
            "project unregistered",
            project_id=str(inp.project_id),
            folder=str(project.folder),
        )
