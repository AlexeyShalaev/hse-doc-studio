from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.repositories import (
    IFileRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class CreateDirInput:
    project_id: UUID
    path: str


class CreateDirUC:
    """Creates an empty directory inside a project. Not VCS-tracked — git does
    not record empty directories, so a snapshot here would be a no-op."""

    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
    ) -> None:
        self._file_repo = file_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: CreateDirInput) -> None:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        self._file_repo.mkdir(project.folder, inp.path)
        logger.debug("dir created via use case", project_id=str(inp.project_id), path=inp.path)
