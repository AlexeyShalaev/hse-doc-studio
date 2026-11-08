"""Персоны смотрящего для плана подписей: локально человек один, на сервере персона из членства в проекте."""

from __future__ import annotations

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.signatures.plan import author_personas, grant_personas


class LocalSignerScope:
    async def personas(self, project: Project) -> frozenset[str]:
        return author_personas(project)


class ServerSignerScope:
    def __init__(self, acl: IProjectAclRepository) -> None:
        self._acl = acl

    async def personas(self, project: Project) -> frozenset[str]:
        actor = current_actor()
        if actor is None:
            return frozenset()
        if actor.is_local:
            return author_personas(project)
        loaded = await self._acl.load_for(actor, project.id)
        return grant_personas(project, loaded.grant_for(actor) if loaded is not None else None)
