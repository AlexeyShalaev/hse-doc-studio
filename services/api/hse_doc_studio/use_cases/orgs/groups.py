"""Группы внутри организации и их состав. Группой управляет админ организации, видят её все участники."""

from __future__ import annotations

import uuid

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.orgs.entities import GROUP_NAME_MAX, Group, GroupMemberView, GroupSummary, OrgRole
from hse_doc_studio.core.orgs.protocols import IGroupRepository, IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import OrgContext, load_context, load_context_by_slug, require_role
from hse_doc_studio.use_cases.orgs.orgs import clean_name


class _GroupAccess:
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository) -> None:
        self._orgs = orgs
        self._groups = groups

    async def context(self, actor: Actor, group_id: str) -> tuple[Group, OrgContext]:
        """Группа чужой организации неотличима от несуществующей."""
        group = await self._groups.get(group_id)
        if group is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return group, await load_context(self._orgs, actor, await self._orgs.get(group.org_id))


class ListGroupsUC:
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository) -> None:
        self._orgs = orgs
        self._groups = groups

    async def execute(self, actor: Actor, slug: str) -> list[GroupSummary]:
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        return await self._groups.list_for_org(ctx.org.id)


class CreateGroupUC:
    def __init__(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork, clock: Clock = utc_now
    ) -> None:
        self._orgs = orgs
        self._groups = groups
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, slug: str, *, name: str) -> GroupSummary:
        ctx = await load_context_by_slug(self._orgs, actor, slug)
        require_role(ctx, OrgRole.admin)
        group = Group(
            id=f"grp_{uuid.uuid4().hex}",
            org_id=ctx.org.id,
            name=clean_name(name, GROUP_NAME_MAX),
            created_at=self._clock(),
        )
        async with self._uow.begin():
            await self._groups.add(group)
            await self._audit.record(
                "group.create",
                actor_id=ctx.me.user_id,
                target=group.id,
                details={"org": ctx.org.slug, "name": group.name},
            )
        return GroupSummary(group, 0)


class UpdateGroupUC(_GroupAccess):
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs, groups)
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, group_id: str, *, name: str) -> GroupSummary:
        group, ctx = await self.context(actor, group_id)
        require_role(ctx, OrgRole.admin)
        renamed = Group(group.id, group.org_id, clean_name(name, GROUP_NAME_MAX), group.created_at, group.external_ref)
        async with self._uow.begin():
            await self._groups.update(renamed)
            await self._audit.record(
                "group.update", actor_id=ctx.me.user_id, target=group.id, details={"name": renamed.name}
            )
        members = await self._groups.list_members(group.id)
        return GroupSummary(renamed, len(members))


class DeleteGroupUC(_GroupAccess):
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs, groups)
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, group_id: str) -> None:
        group, ctx = await self.context(actor, group_id)
        require_role(ctx, OrgRole.admin)
        async with self._uow.begin():
            await self._groups.delete(group.id)
            await self._audit.record(
                "group.delete", actor_id=ctx.me.user_id, target=group.id, details={"org": ctx.org.slug}
            )


class ListGroupMembersUC(_GroupAccess):
    async def execute(self, actor: Actor, group_id: str) -> list[GroupMemberView]:
        group, _ = await self.context(actor, group_id)
        return await self._groups.list_members(group.id)


class AddGroupMemberUC(_GroupAccess):
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs, groups)
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, group_id: str, *, user_id: str) -> GroupMemberView:
        """В группу входят только участники её организации."""
        group, ctx = await self.context(actor, group_id)
        require_role(ctx, OrgRole.admin)
        if await self._orgs.get_member(group.org_id, user_id) is None:
            raise IdentityError(IdentityErrorCode.user_not_found)
        async with self._uow.begin():
            await self._groups.add_member(group.id, user_id)
            await self._audit.record(
                "group.member.add", actor_id=ctx.me.user_id, target=group.id, details={"user_id": user_id}
            )
        added = next(m for m in await self._groups.list_members(group.id) if m.user_id == user_id)
        return added


class RemoveGroupMemberUC(_GroupAccess):
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs, groups)
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, group_id: str, user_id: str) -> None:
        group, ctx = await self.context(actor, group_id)
        require_role(ctx, OrgRole.admin)
        async with self._uow.begin():
            if not await self._groups.remove_member(group.id, user_id):
                raise IdentityError(IdentityErrorCode.not_found)
            await self._audit.record(
                "group.member.remove", actor_id=ctx.me.user_id, target=group.id, details={"user_id": user_id}
            )
