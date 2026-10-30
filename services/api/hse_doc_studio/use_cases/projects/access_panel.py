"""Панель «Доступ» проекта: кто имеет доступ и кого можно добавить. Права на вызов проверяет гард маршрута."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.repositories import IProjectAccessDirectory, ProjectAccessRow, ProjectCandidate
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.orgs.access import user_id_of

CANDIDATES_LIMIT = 12


class ListProjectAccessUC:
    def __init__(self, directory: IProjectAccessDirectory) -> None:
        self._directory = directory

    async def execute(self, project_id: UUID) -> list[ProjectAccessRow]:
        rows = await self._directory.list_access(project_id)
        if not rows:
            raise IdentityError(IdentityErrorCode.not_found)
        return rows


class ListAccessCandidatesUC:
    def __init__(self, directory: IProjectAccessDirectory) -> None:
        self._directory = directory

    async def execute(self, actor: Actor, project_id: UUID, query: str) -> list[ProjectCandidate]:
        return await self._directory.candidates(project_id, user_id_of(actor), query, CANDIDATES_LIMIT)
