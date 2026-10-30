"""Организации в админке установки: админ управляет ими без членства, роль в организации ему не нужна.

Правила те же, что у `/orgs`: адрес организации не меняется, организацию с проектами не удалить, последний
владелец остаётся. Отличие одно: админ установки распоряжается всеми ролями, включая владельцев.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.protocols import IAuditLog, IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.orgs.entities import (
    GROUP_NAME_MAX,
    ORG_NAME_MAX,
    AdminOrgSummary,
    Group,
    Org,
    OrgMember,
    OrgMemberView,
    OrgRole,
)
from hse_doc_studio.core.orgs.protocols import IGroupRepository, IOrgRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.orgs.orgs import check_slug, clean_name


class AdminGroupView:
    """Группа с id участников: так её отдаёт админка."""

    def __init__(self, group: Group, member_ids: Sequence[str]) -> None:
        self.group = group
        self.member_ids = list(member_ids)


class _AdminOrgs:
    def __init__(self, orgs: IOrgRepository) -> None:
        self._orgs = orgs

    async def org(self, slug: str) -> Org:
        found = await self._orgs.get_by_slug(slug)
        if found is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return found

    async def summary(self, org: Org, admin_id: str) -> AdminOrgSummary:
        return await self._orgs.summary_for_admin(org, admin_id)

    async def keep_an_owner(self, org: Org, leaving: OrgMember) -> None:
        """Вызывается в транзакции до записи: владельцы блокируются, и последний из них остаётся."""
        if leaving.role is OrgRole.owner and await self._orgs.lock_owners(org.id) == [leaving.user_id]:
            raise IdentityError(IdentityErrorCode.last_owner)

    async def member(self, org: Org, user_id: str) -> OrgMember:
        found = await self._orgs.get_member(org.id, user_id)
        if found is None:
            raise IdentityError(IdentityErrorCode.not_found)
        return found


class ListAdminOrgsUC:
    def __init__(self, orgs: IOrgRepository) -> None:
        self._orgs = orgs

    async def execute(self, actor: Actor) -> list[AdminOrgSummary]:
        return await self._orgs.list_all(require_admin(actor))


class GetAdminOrgUC(_AdminOrgs):
    async def execute(self, actor: Actor, slug: str) -> AdminOrgSummary:
        admin_id = require_admin(actor)
        return await self.summary(await self.org(slug), admin_id)


class CreateAdminOrgUC(_AdminOrgs):
    def __init__(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork, clock: Clock = utc_now) -> None:
        super().__init__(orgs)
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, *, slug: str, name: str) -> AdminOrgSummary:
        """Создатель становится владельцем: без владельца организацию некому вести."""
        admin_id = require_admin(actor)
        value = check_slug(slug)
        now = self._clock()
        org = Org(
            id=f"org_{uuid.uuid4().hex}",
            slug=value,
            name=clean_name(name, ORG_NAME_MAX),
            created_at=now,
            created_by=admin_id,
        )
        async with self._uow.begin():
            await self._orgs.add(org)
            await self._orgs.add_member(OrgMember(org.id, admin_id, OrgRole.owner, now))
            await self._audit.record("org.create", actor_id=admin_id, target=org.id, details={"slug": value})
        return await self.summary(org, admin_id)


class DeleteAdminOrgUC(_AdminOrgs):
    def __init__(self, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs)
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, slug: str) -> None:
        admin_id = require_admin(actor)
        org = await self.org(slug)
        async with self._uow.begin():
            if await self._orgs.count_projects(org.id) > 0:
                raise IdentityError(IdentityErrorCode.org_has_projects)
            await self._orgs.delete(org.id)
            await self._audit.record("org.delete", actor_id=admin_id, target=org.id, details={"slug": org.slug})


class ListAdminMembersUC(_AdminOrgs):
    async def execute(self, actor: Actor, slug: str) -> list[OrgMemberView]:
        require_admin(actor)
        return await self._orgs.list_members((await self.org(slug)).id)


class AddAdminMemberUC(_AdminOrgs):
    def __init__(
        self, orgs: IOrgRepository, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork, clock: Clock = utc_now
    ) -> None:
        super().__init__(orgs)
        self._users = users
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, slug: str, *, email: str, role: OrgRole) -> OrgMemberView:
        admin_id = require_admin(actor)
        org = await self.org(slug)
        user = await self._users.get_by_email(normalize_email(email))
        if user is None or not user.can_sign_in:
            raise IdentityError(IdentityErrorCode.user_not_found)
        member = OrgMember(org.id, user.id, role, self._clock())
        async with self._uow.begin():
            await self._orgs.add_member(member)
            await self._audit.record(
                "org.member.add", actor_id=admin_id, target=org.id, details={"user_id": user.id, "role": role.value}
            )
        return OrgMemberView(member, user.name, user.email)


class SetAdminMemberRoleUC(_AdminOrgs):
    def __init__(self, orgs: IOrgRepository, users: IUserRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs)
        self._users = users
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, slug: str, user_id: str, *, role: OrgRole) -> OrgMemberView:
        admin_id = require_admin(actor)
        org = await self.org(slug)
        async with self._uow.begin():
            target = await self.member(org, user_id)
            if role is not OrgRole.owner:
                await self.keep_an_owner(org, target)
            if role is not target.role:
                await self._orgs.set_role(org.id, user_id, role)
                await self._audit.record(
                    "org.member.role",
                    actor_id=admin_id,
                    target=org.id,
                    details={"user_id": user_id, "from": target.role.value, "to": role.value},
                )
        user = await self._users.get(user_id)
        return OrgMemberView(
            OrgMember(org.id, user_id, role, target.created_at),
            user.name if user else "",
            user.email if user else "",
        )


class RemoveAdminMemberUC(_AdminOrgs):
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs)
        self._groups = groups
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, slug: str, user_id: str) -> None:
        """Убирает участника и его членство в группах организации."""
        admin_id = require_admin(actor)
        org = await self.org(slug)
        async with self._uow.begin():
            target = await self.member(org, user_id)
            await self.keep_an_owner(org, target)
            await self._orgs.remove_member(org.id, user_id)
            await self._groups.remove_user_from_org_groups(org.id, user_id)
            await self._audit.record(
                "org.member.remove", actor_id=admin_id, target=org.id, details={"user_id": user_id}
            )


class _AdminGroups(_AdminOrgs):
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository) -> None:
        super().__init__(orgs)
        self._groups = groups

    async def group(self, org: Org, group_id: str) -> Group:
        """Группа другой организации неотличима от несуществующей."""
        found = await self._groups.get(group_id)
        if found is None or found.org_id != org.id:
            raise IdentityError(IdentityErrorCode.not_found)
        return found

    async def valid_members(self, org: Org, member_ids: Sequence[str]) -> list[str]:
        """В группу входят только участники организации; повторы схлопываются."""
        unique = list(dict.fromkeys(member_ids))
        known = {m.member.user_id for m in await self._orgs.list_members(org.id)}
        if not set(unique) <= known:
            raise IdentityError(IdentityErrorCode.input_invalid)
        return unique

    async def sync_members(self, group: Group, wanted: Sequence[str]) -> None:
        current = {m.user_id for m in await self._groups.list_members(group.id)}
        for user_id in wanted:
            if user_id not in current:
                await self._groups.add_member(group.id, user_id)
        for user_id in current - set(wanted):
            await self._groups.remove_member(group.id, user_id)


class ListAdminGroupsUC(_AdminGroups):
    async def execute(self, actor: Actor, slug: str) -> list[AdminGroupView]:
        require_admin(actor)
        org = await self.org(slug)
        members = await self._groups.member_ids_by_org(org.id)
        return [AdminGroupView(g.group, members.get(g.group.id, [])) for g in await self._groups.list_for_org(org.id)]


class CreateAdminGroupUC(_AdminGroups):
    def __init__(
        self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork, clock: Clock = utc_now
    ) -> None:
        super().__init__(orgs, groups)
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, slug: str, *, name: str, member_ids: Sequence[str]) -> AdminGroupView:
        admin_id = require_admin(actor)
        org = await self.org(slug)
        wanted = await self.valid_members(org, member_ids)
        group = Group(
            id=f"grp_{uuid.uuid4().hex}",
            org_id=org.id,
            name=clean_name(name, GROUP_NAME_MAX),
            created_at=self._clock(),
        )
        async with self._uow.begin():
            await self._groups.add(group)
            await self.sync_members(group, wanted)
            await self._audit.record(
                "group.create",
                actor_id=admin_id,
                target=group.id,
                details={"org": org.slug, "name": group.name, "members": len(wanted)},
            )
        return AdminGroupView(group, wanted)


class UpdateAdminGroupUC(_AdminGroups):
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs, groups)
        self._audit = audit
        self._uow = uow

    async def execute(
        self, actor: Actor, slug: str, group_id: str, *, name: str | None, member_ids: Sequence[str] | None
    ) -> AdminGroupView:
        """Меняется только заданное; состав заменяется целиком."""
        admin_id = require_admin(actor)
        org = await self.org(slug)
        group = await self.group(org, group_id)
        wanted = await self.valid_members(org, member_ids) if member_ids is not None else None
        renamed = (
            Group(group.id, group.org_id, clean_name(name, GROUP_NAME_MAX), group.created_at, group.external_ref)
            if name is not None
            else group
        )
        async with self._uow.begin():
            if renamed is not group:
                await self._groups.update(renamed)
            if wanted is not None:
                await self.sync_members(group, wanted)
            await self._audit.record(
                "group.update",
                actor_id=admin_id,
                target=group.id,
                details={"name": renamed.name, "members": len(wanted) if wanted is not None else None},
            )
        members = wanted if wanted is not None else [m.user_id for m in await self._groups.list_members(group.id)]
        return AdminGroupView(renamed, members)


class DeleteAdminGroupUC(_AdminGroups):
    def __init__(self, orgs: IOrgRepository, groups: IGroupRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        super().__init__(orgs, groups)
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, slug: str, group_id: str) -> None:
        admin_id = require_admin(actor)
        org = await self.org(slug)
        group = await self.group(org, group_id)
        async with self._uow.begin():
            await self._groups.delete(group.id)
            await self._audit.record("group.delete", actor_id=admin_id, target=group.id, details={"org": org.slug})
