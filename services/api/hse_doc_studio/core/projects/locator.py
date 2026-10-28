"""Порт поиска папки проекта по id.

В локальном режиме проекты лежат в выбранных пользователем папках, а их список
в `projects.json`, поэтому id находится перебором. В серверном режиме порт
отвечает запросом к таблице projects, и с диска ничего не читается.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import Project


class IProjectLocator(Protocol):
    async def folder_of(self, project_id: UUID) -> Path | None: ...

    async def locate(self, project_id: UUID) -> tuple[Path, Project] | None:
        """Папка и проект сразу; None, если проекта нет или он не читается."""
        ...

    async def list_visible(self, actor: Actor | None) -> list[Path]:
        """Папки проектов, доступных актору, в порядке регистрации.

        None значит «запроса нет»: серверная реализация в этом случае отказывает, локальная актора не смотрит.
        """
        ...

    async def list_all(self) -> list[Path]:
        """Все папки в порядке регистрации, без учёта доступа: только для системных путей (восстановление, сканы)."""
        ...

    async def register(self, folder: Path) -> None: ...

    async def unregister(self, folder: Path) -> None: ...
