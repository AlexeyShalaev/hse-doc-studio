from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

import structlog

from hse_doc_studio.core.access.context import ActorRequired, current_actor
from hse_doc_studio.core.access.repositories import IProjectMemberships, ProjectMembership
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IProjectRepository,
)

logger = structlog.get_logger()


@dataclass
class ListProjectsOutput:
    projects: list[Project]
    # Заполнено только на сервере: владелец и роль актора по id проекта.
    memberships: dict[UUID, ProjectMembership] = field(default_factory=dict)


class ListProjectsUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        locator: IProjectLocator,
        memberships: IProjectMemberships | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._locator = locator
        self._memberships = memberships

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

        if self._memberships is None:
            return ListProjectsOutput(projects=projects)
        actor = current_actor()
        if actor is None:
            raise ActorRequired("список проектов без актора")
        found = await self._memberships.memberships_for(actor, [p.id for p in projects])
        # Проект без членства (удалён между запросами) в ответ не попадает.
        return ListProjectsOutput(projects=[p for p in projects if p.id in found], memberships=found)
