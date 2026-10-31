"""Допуск к комнате совместной правки: кто подключается и вправе ли он писать.

Читает комнату тот, кто читает файл; пишет тот, кто вправе править этот путь и при этом проект не заперт
(только чтение, обновление шаблона). Право пересматривается во время сессии: понижение роли отключает или
переводит в чтение.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.projects.get_project_access import GetProjectAccessInput, GetProjectAccessUC


@dataclass(frozen=True)
class CollabAccess:
    can_write: bool
    key: str
    name: str


class AuthorizeCollabUC:
    def __init__(self, access: IProjectAccessChecker, project_access: GetProjectAccessUC) -> None:
        self._access = access
        self._project_access = project_access

    async def execute(self, project_id: UUID, path: str) -> CollabAccess:
        """NotFoundError: проекта нет или он чужой; ProjectForbiddenError: файл читать нельзя."""
        await self._access.require(project_id, Action.FILES_READ, path)
        actor = require_actor()
        writable = await self._may_write(project_id, path)
        key = actor.id or "local"
        return CollabAccess(can_write=writable, key=key, name=(actor.name or actor.email or "").strip() or "?")

    async def _may_write(self, project_id: UUID, path: str) -> bool:
        try:
            await self._access.require(project_id, Action.FILES_WRITE, path)
        except ProjectForbiddenError:
            return False
        try:
            result = await self._project_access.execute(GetProjectAccessInput(project_id=project_id))
        except NotFoundError:
            return False
        return result.access.writable
