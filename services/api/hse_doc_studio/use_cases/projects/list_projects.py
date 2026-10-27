from __future__ import annotations

from dataclasses import dataclass

import structlog

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
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
        locator: IProjectLocator,
    ) -> None:
        self._project_repo = project_repo
        self._locator = locator

    async def execute(self) -> ListProjectsOutput:
        known_folders = await self._locator.list_visible(current_actor())
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
