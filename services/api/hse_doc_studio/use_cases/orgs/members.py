"""Участники организации: добавление существующего аккаунта, смена роли, удаление, выход."""

from __future__ import annotations

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.orgs.entities import OrgMember, OrgMemberView, OrgRole
from hse_doc_studio.core.orgs.protocols import IGroupRepository, IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import OrgContext, can_manage_member, load_context_by_slug, require_role


class ListOrgMembersUC:
    def __init__(self, orgs: IOrgRepository) -> None:
        self._orgs = orgs

    async def execute(self, actor: Actor, slug: str) -> list[OrgMemberView]:
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        return await self._orgs.list_members(ctx.org.id)


class AddOrgMemberUC:
    def __init__(
        self, orgs: IOrgRepository, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork, clock: Clock = utc_now
    ) -> None:
        self._orgs = orgs
        self._users = users
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, slug: str, *, email: str, role: OrgRole) -> OrgMemberView:
        """Добавляет существующий аккаунт сразу, без подтверждения со стороны человека (решение этапа 2).
        Админ добавляет обычных участников, владелец любых."""
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        require_role(ctx, OrgRole.admin)
        if not can_manage_member(ctx.me.role, role, role):
            raise IdentityError(IdentityErrorCode.forbidden)
        user = await self._users.get_by_email(normalize_email(email))
        if user is None or not user.can_sign_in:
            raise IdentityError(IdentityErrorCode.user_not_found)
        member = OrgMember(ctx.org.id, user.id, role, self._clock())
        async with self._uow.begin():
            await self._orgs.add_member(member)
            await self._audit.record(
                "org.member.add",
                actor_id=ctx.me.user_id,
                target=ctx.org.id,
                details={"user_id": user.id, "role": role.value},
            )
        return OrgMemberView(member, user.name, user.email)


async def _target(orgs: IOrgRepository, ctx: OrgContext, user_id: str) -> OrgMember:
    member = await orgs.get_member(ctx.org.id, user_id)
    if member is None:
        raise IdentityError(IdentityErrorCode.not_found)
    return member


async def _keep_an_owner(orgs: IOrgRepository, ctx: OrgContext, leaving: OrgMember) -> None:
    """Вызывается в транзакции до записи: владельцы блокируются, и последний из них остаётся."""
    if leaving.role is not OrgRole.owner:
        return
    if await orgs.lock_owners(ctx.org.id) == [leaving.user_id]:
        raise IdentityError(IdentityErrorCode.last_owner)


class ChangeOrgRoleUC:
    def __init__(self, orgs: IOrgRepository, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._orgs = orgs
        self._users = users
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, slug: str, user_id: str, *, role: OrgRole) -> OrgMemberView:
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        require_role(ctx, OrgRole.admin)
        async with self._uow.begin():
            target = await _target(self._orgs, ctx, user_id)
            if not can_manage_member(ctx.me.role, target.role, role):
                raise IdentityError(IdentityErrorCode.forbidden)
            if role is not OrgRole.owner:
                await _keep_an_owner(self._orgs, ctx, target)
            if role is not target.role:
                await self._orgs.set_role(ctx.org.id, user_id, role)
                await self._audit.record(
                    "org.member.role",
                    actor_id=ctx.me.user_id,
                    target=ctx.org.id,
                    details={"user_id": user_id, "from": target.role.value, "to": role.value},
                )
        user = await self._users.get(user_id)
        return OrgMemberView(
            OrgMember(ctx.org.id, user_id, role, target.created_at),
            user.name if user else "",
            user.email if user else "",
        )


class _Leaving:
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._orgs = orgs
        self._groups = groups
        self._audit = audit
        self._uow = uow

    async def remove(self, ctx: OrgContext, target: OrgMember, action: str) -> None:
        async with self._uow.begin():
            await _keep_an_owner(self._orgs, ctx, target)
            await self._orgs.remove_member(ctx.org.id, target.user_id)
            await self._groups.remove_user_from_org_groups(ctx.org.id, target.user_id)
            await self._audit.record(
                action, actor_id=ctx.me.user_id, target=ctx.org.id, details={"user_id": target.user_id}
            )


class RemoveOrgMemberUC(_Leaving):
    async def execute(self, actor: Actor, slug: str, user_id: str) -> None:
        """Убирает участника вместе с его членством в группах. Себя можно убрать всегда (как «выйти»),
        остальных админ организации (обычных участников) или владелец; последнего владельца убрать нельзя."""
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        target = await _target(self._orgs, ctx, user_id)
        if target.user_id != ctx.me.user_id:
            require_role(ctx, OrgRole.admin)
            if not can_manage_member(ctx.me.role, target.role):
                raise IdentityError(IdentityErrorCode.forbidden)
        await self.remove(ctx, target, "org.member.remove")


class LeaveOrgUC(_Leaving):
    async def execute(self, actor: Actor, slug: str) -> None:
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        await self.remove(ctx, ctx.me, "org.member.leave")
