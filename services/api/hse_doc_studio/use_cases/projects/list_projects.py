from __future__ import annotations

from dataclasses import dataclass

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.repositories import (
    IProjectIndexRepository,
    IProjectRepository,
)

logger = structlog.get_logger()


@dataclass
class ListProjectsOutput:
    projects: list[Project]


class ListProjectsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo

    async def execute(self) -> ListProjectsOutput:
        known_folders = self._project_index_repo.list_known()
        projects: list[Project] = []

        for folder in known_folders:
            try:
                project = self._project_repo.get(folder)
                if project is None:
                    logger.warning(
                        "project.json not found or broken, skipping",
                        folder=str(folder),
                    )
                    continue
                projects.append(project)
            except Exception as exc:
                logger.warning(
                    "error loading project, skipping",
                    folder=str(folder),
                    exc=str(exc),
                )

        return ListProjectsOutput(projects=projects)
