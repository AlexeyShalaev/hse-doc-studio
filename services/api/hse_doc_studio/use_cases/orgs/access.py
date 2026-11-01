"""Права в организации: кто видит организацию и что может делать. Не участнику 404, мало роли 403."""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import Org, OrgMember, OrgRole
from hse_doc_studio.core.orgs.protocols import IOrgRepository


@dataclass(frozen=True)
class OrgContext:
    org: Org
    me: OrgMember


def user_id_of(actor: Actor) -> str:
    if actor.kind is not ActorKind.user or actor.id is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor.id


async def load_context(orgs: IOrgRepository, actor: Actor, org: Org | None) -> OrgContext:
    """Организация и членство актора. Админ установки без членства организацию через этот API не видит:
    её содержимое ему открывает только явное членство (управление установкой идёт через `/api/admin`)."""
    user_id = user_id_of(actor)
    me = await orgs.get_member(org.id, user_id) if org is not None else None
    if org is None or me is None:
        raise IdentityError(IdentityErrorCode.not_found)
    return OrgContext(org, me)


async def load_context_by_slug(orgs: IOrgRepository, actor: Actor, slug: str) -> OrgContext:
    return await load_context(orgs, actor, await orgs.get_by_slug(slug))


def require_role(ctx: OrgContext, minimum: OrgRole) -> None:
    if ctx.me.role.rank < minimum.rank:
        raise IdentityError(IdentityErrorCode.forbidden)


def can_manage_member(actor_role: OrgRole, target_role: OrgRole, new_role: OrgRole | None = None) -> bool:
    """Владелец управляет всеми; админ только обычными участниками и не повышает их выше участника."""
    if actor_role is OrgRole.owner:
        return True
    return actor_role is OrgRole.admin and target_role is OrgRole.member and new_role in (None, OrgRole.member)
