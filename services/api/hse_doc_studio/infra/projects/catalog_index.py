"""Индекс проектов серверного режима поверх каталога в Postgres."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.projects.locator import IProjectLocator


class CatalogProjectIndex:
    """Замена локального ``projects.json``: сценарии ищут проект по id через каталог, а не перебором папок.

    Список папок и регистрация здесь пусты намеренно: папку выделяет и учитывает ``IProjectLocator``
    (``projects_root/<id>`` плюс строка в ``projects``), поэтому синхронный список не нужен и столкнуться
    с чужой папкой нельзя.
    """

    def __init__(self, locator: IProjectLocator) -> None:
        self._locator = locator

    async def locate(self, project_id: UUID) -> tuple[Path, Project] | None:
        return await self._locator.locate(project_id)

    def list_known(self) -> list[Path]:
        return []

    def register(self, folder: Path) -> None:
        return None

    def unregister(self, folder: Path) -> None:
        return None
