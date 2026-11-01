"""Плательщик сборки (S7): от чьего имени, в чью квоту и по чьему маршруту раннеров ставится задача."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.context import ActorRequired
from hse_doc_studio.core.access.entities import Actor, ActorKind, Role
from hse_doc_studio.core.access.links import IShareLinkStore
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode


def _uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ActorRequired(f"неверный id пользователя: {value!r}") from exc


class GuestBuildPayer:
    """Пользователь платит сам. Гость по ссылке ставит сборку от имени создателя ссылки, если тот ещё вправе
    делиться проектом; иначе от имени владельца-человека; у проекта организации без создателя отказ
    `guest_build_unavailable` (409)."""

    def __init__(self, store: IShareLinkStore, acl: IProjectAclRepository) -> None:
        self._store = store
        self._acl = acl

    async def payer_for(self, actor: Actor, project_id: UUID) -> UUID:
        if actor.kind is ActorKind.user and actor.id is not None:
            return _uuid(actor.id)
        if actor.kind is not ActorKind.guest or actor.link_id is None:
            raise ActorRequired("задача очереди ставится только от имени пользователя или гостя по ссылке")
        link = await self._store.get(actor.link_id)
        if link is not None and link.created_by is not None and await self._may_share(link.created_by, project_id):
            return _uuid(link.created_by)
        project = await self._store.project(project_id)
        if project is not None and project.owner_user_id is not None:
            return _uuid(project.owner_user_id)
        raise IdentityError(IdentityErrorCode.guest_build_unavailable)

    async def _may_share(self, user_id: str, project_id: UUID) -> bool:
        creator = Actor.user(user_id)
        acl = await self._acl.load_for(creator, project_id, include_links=False)
        grant = acl.grant_for(creator) if acl is not None else None
        return grant is not None and (grant.role is Role.owner or grant.can_share)
