from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
class GetFileInput:
    project_id: UUID
    path: str


@dataclass
class GetFileOutput:
    content: bytes
    filename: str


class GetFileUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        file_repo: IFileRepository,
    ) -> None:
        self._file_repo = file_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: GetFileInput) -> GetFileOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        content = self._file_repo.read(project.folder, inp.path)
        filename = Path(inp.path).name

        return GetFileOutput(content=content, filename=filename)
