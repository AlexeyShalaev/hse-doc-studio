"""Порт членства проекта: права актора берутся только из хранилища сервера."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor, ProjectAcl


class IProjectAclRepository(Protocol):
    async def load_for(self, actor: Actor, project_id: UUID) -> ProjectAcl | None:
        """Членство проекта для одного актора; None, если проекта нет или актор не участник.

        В `grants` лежит единственная запись: право самого актора. Поля team и shared_enabled
        берутся из БД, `project.json` источником прав не служит.
        """
        ...

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        """Единственный путь записи флага общих документов: файл потом перезаписывается значением из БД."""
        ...
