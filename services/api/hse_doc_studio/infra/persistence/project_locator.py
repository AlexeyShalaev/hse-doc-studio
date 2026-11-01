from __future__ import annotations

from pathlib import Path
from uuid import UUID

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository

logger = structlog.get_logger()


class LocalProjectLocator:
    """Перебор зарегистрированных папок: проект ищется по id в project.json каждой."""

    def __init__(self, index: IProjectIndexRepository, projects: IProjectRepository) -> None:
        self._index = index
        self._projects = projects

    async def folder_of(self, project_id: UUID) -> Path | None:
        found = await self.locate(project_id)
        return None if found is None else found[0]

    async def locate(self, project_id: UUID) -> tuple[Path, Project] | None:
        for folder in self._index.list_known():
            try:
                project = self._projects.get(folder)
            except Exception as exc:  # noqa: BLE001 — один битый проект не должен скрывать остальные
                logger.warning("project locator: error loading project", folder=str(folder), exc=str(exc))
                continue
            if project is not None and project.id == project_id:
                return folder, project
        return None

    async def list_visible(self, actor: Actor | None) -> list[Path]:
        return self._index.list_known()

    async def list_all(self) -> list[Path]:
        return self._index.list_known()

    async def register(self, folder: Path) -> None:
        self._index.register(folder)

    async def unregister(self, folder: Path) -> None:
        self._index.unregister(folder)
