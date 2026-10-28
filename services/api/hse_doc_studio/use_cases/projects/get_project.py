from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import structlog

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


class GetProjectUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo

    async def execute(self, inp: GetProjectInput) -> GetProjectOutput:
        index = self._project_index_repo
        if isinstance(index, IProjectIndexLookup):
            # Серверный режим: проект ищет каталог в БД, папок индекса там нет.
            found = await index.locate(inp.project_id)
            if found is not None:
                return GetProjectOutput(project=found[1])
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
