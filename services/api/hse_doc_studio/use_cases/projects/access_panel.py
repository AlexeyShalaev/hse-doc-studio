"""Панель «Доступ» проекта: кто имеет доступ и кого можно добавить. Права на вызов проверяет гард маршрута."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.access.repositories import (
    AccessQuery,
    IProjectAccessDirectory,
    ProjectAccessRow,
    ProjectCandidate,
    TransferCandidate,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.listing import PICKER_LIMIT, Found, Picked
from hse_doc_studio.use_cases.orgs.access import user_id_of
from hse_doc_studio.use_cases.sharing.visibility import visible_rows_for


class ListProjectAccessUC:
    def __init__(self, directory: IProjectAccessDirectory) -> None:
        self._directory = directory

    async def execute(self, project_id: UUID, query: AccessQuery) -> Found[ProjectAccessRow]:
        found = await self._directory.page_access(project_id, query)
        if found is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return visible_rows_for(current_actor(), found)


class ListAccessCandidatesUC:
    """Пикер «Добавить»: первые `limit` (до 20) и признак «есть ещё»; охват общими организациями не меняется."""

    def __init__(self, directory: IProjectAccessDirectory) -> None:
        self._directory = directory

    async def execute(
        self,
        actor: Actor,
        project_id: UUID,
        query: str,
        *,
        limit: int = PICKER_LIMIT,
        kind: Literal["user", "group"] | None = None,
    ) -> Picked[ProjectCandidate]:
        return await self._directory.candidates(project_id, user_id_of(actor), query, limit, kind)


class ListTransferCandidatesUC:
    """Кому передать проект: организации, где смотрящий владелец или админ, и люди общих организаций."""

    def __init__(self, directory: IProjectAccessDirectory) -> None:
        self._directory = directory

    async def execute(
        self,
        actor: Actor,
        project_id: UUID,
        query: str,
        *,
        limit: int = PICKER_LIMIT,
        kind: Literal["user", "org"] | None = None,
    ) -> Picked[TransferCandidate]:
        return await self._directory.transfer_candidates(project_id, user_id_of(actor), query, limit, kind)
