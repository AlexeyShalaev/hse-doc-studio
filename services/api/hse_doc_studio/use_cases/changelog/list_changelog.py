from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.entities import ChangeLogEntry
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    IProjectIndexRepository,
    IProjectRepository,
)
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

logger = structlog.get_logger()


@dataclass
class ListChangelogInput:
    project_id: UUID
    doc_id: str | None = None
    limit: int = 50
    offset: int = 0


@dataclass
class ListChangelogOutput:
    entries: list[ChangeLogEntry]


class ListChangelogUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        changelog_repo: IChangeLogRepository,
    ) -> None:
        self._changelog_repo = changelog_repo
        self._get_uc = GetProjectUC(project_repo, project_index_repo)

    async def execute(self, inp: ListChangelogInput) -> ListChangelogOutput:
        result = await self._get_uc.execute(GetProjectInput(project_id=inp.project_id))
        project = result.project

        entries = self._changelog_repo.list(project.folder, inp.doc_id)
        # Newest first
        entries = list(reversed(entries))
        # Apply pagination
        paginated = entries[inp.offset : inp.offset + inp.limit]

        return ListChangelogOutput(entries=paginated)
