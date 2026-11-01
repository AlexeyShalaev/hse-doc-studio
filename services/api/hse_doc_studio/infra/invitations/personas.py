"""Персоны проекта для приглашений: слаги авторов из `project.json` и роли руководителей."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.invitations.entities import SUPERVISOR_PERSONAS
from hse_doc_studio.core.repositories import IProjectIndexLookup, IProjectIndexRepository


class ProjectFilePersonas:
    def __init__(self, index: IProjectIndexRepository) -> None:
        self._index = index

    async def personas(self, project_id: UUID) -> frozenset[str] | None:
        if not isinstance(self._index, IProjectIndexLookup):
            return None
        found = await self._index.locate(project_id)
        if found is None:
            return None
        project = found[1]
        return frozenset(a.slug for a in project.authors if a.slug) | SUPERVISOR_PERSONAS
