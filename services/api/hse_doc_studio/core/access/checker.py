"""Порт проверки прав на проект, чей id лежит не в пути, а в теле запроса.

Гард маршрутов видит только `project_id` из пути. Когда id приходит в теле (чат агента, проверка адреса
репозитория для существующего проекта), право проверяет сам сценарий через этот порт: чужой и
несуществующий проект дают NotFoundError (ответ 404), нехватка роли даёт ProjectForbiddenError (403).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Role


class ProjectForbiddenError(Exception):
    """Актор участник проекта, но его роли для действия не хватает.

    `required_role` задан, когда отказ объясняется ролью: клиент называет её в сообщении.
    """

    def __init__(self, message: str = "Forbidden", required_role: Role | None = None) -> None:
        super().__init__(message)
        self.required_role = required_role


class IProjectAccessChecker(Protocol):
    async def require(self, project_id: UUID, action: Action) -> None: ...
