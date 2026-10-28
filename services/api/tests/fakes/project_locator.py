"""InMemory-реализация IProjectLocator: проекты в словаре, порядок регистрации сохраняется."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import Project


class InMemoryProjectLocator:
    def __init__(self) -> None:
        self._projects: dict[Path, Project] = {}
        self._folders: list[Path] = []

    def add(self, project: Project) -> None:
        self._projects[project.folder] = project
        if project.folder not in self._folders:
            self._folders.append(project.folder)

    async def folder_of(self, project_id: UUID) -> Path | None:
        found = await self.locate(project_id)
        return None if found is None else found[0]

    async def locate(self, project_id: UUID) -> tuple[Path, Project] | None:
        for folder in self._folders:
            project = self._projects.get(folder)
            if project is not None and project.id == project_id:
                return folder, project
        return None

    async def list_visible(self, actor: Actor | None) -> list[Path]:
        return list(self._folders)

    async def list_all(self) -> list[Path]:
        return list(self._folders)

    async def register(self, folder: Path) -> None:
        if folder not in self._folders:
            self._folders.append(folder)

    async def unregister(self, folder: Path) -> None:
        if folder in self._folders:
            self._folders.remove(folder)
