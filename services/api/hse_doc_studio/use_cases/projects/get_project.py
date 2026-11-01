from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

from hse_doc_studio.core.access.context import ActorRequired, current_actor
from hse_doc_studio.core.access.repositories import IProjectMemberships, ProjectMembership
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IProjectIndexLookup,
    IProjectIndexRepository,
    IProjectRepository,
)

logger = structlog.get_logger()


@dataclass
class GetProjectInput:
    project_id: UUID


@dataclass
class GetProjectOutput:
    project: Project
    # Только на сервере: владелец проекта и роль актора, как в списке проектов.
    membership: ProjectMembership | None = None


class GetProjectUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        memberships: IProjectMemberships | None = None,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._memberships = memberships

    async def execute(self, inp: GetProjectInput) -> GetProjectOutput:
        index = self._project_index_repo
        if isinstance(index, IProjectIndexLookup):
            # Серверный режим: проект ищет каталог в БД, папок индекса там нет.
            found = await index.locate(inp.project_id)
            if found is not None:
                return GetProjectOutput(project=found[1], membership=await self._membership(inp.project_id))
            raise NotFoundError(
                localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
            )

        known_folders = index.list_known()

        for folder in known_folders:
            try:
                project = self._project_repo.get(folder)
                if project is None:
                    continue
                if project.id == inp.project_id:
                    return GetProjectOutput(project=project)
            except Exception as exc:
                logger.warning(
                    "error loading project during search",
                    folder=str(folder),
                    exc=str(exc),
                )

        raise NotFoundError(
            localized_error(f"Проект {inp.project_id!r} не найден", f"Project {inp.project_id!r} not found")
        )

    async def _membership(self, project_id: UUID) -> ProjectMembership | None:
        """Роль смотрящего: по ней интерфейс открывает панели «Доступ» и «Сборки» серверного проекта."""
        if self._memberships is None:
            return None
        actor = current_actor()
        if actor is None:
            raise ActorRequired("проект без актора")
        return (await self._memberships.memberships_for(actor, [project_id])).get(project_id)
