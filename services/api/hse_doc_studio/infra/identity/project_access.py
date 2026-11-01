"""Проверка прав на проект из тела запроса: локально пропускает всех, на сервере читает членство из БД."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.policy import Decision, decide, required_role
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.errors import NotFoundError


class LocalProjectAccessChecker:
    """Локальный режим: актор один и права не ограничены, репозиторий членства не нужен."""

    async def require(self, project_id: UUID, action: Action, path: str | None = None) -> None:
        return None


class ServerProjectAccessChecker:
    async def require(self, project_id: UUID, action: Action, path: str | None = None) -> None:
        actor = require_actor()
        if actor.is_local:
            return
        acl = await self._acl.load_for(actor, project_id)
        decision = decide(actor, action, acl, path)
        if decision is Decision.not_found:
            raise NotFoundError("Project not found")
        if decision is Decision.forbidden:
            raise ProjectForbiddenError("Forbidden", required_role(actor, action, acl))

    def __init__(self, acl: IProjectAclRepository) -> None:
        self._acl = acl
