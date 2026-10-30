from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.orgs.entities import Org, OrgMember, OrgRole
from hse_doc_studio.use_cases.orgs.groups import (
    AddGroupMemberUC,
    CreateGroupUC,
    DeleteGroupUC,
    ListGroupMembersUC,
    ListGroupsUC,
    RemoveGroupMemberUC,
    UpdateGroupUC,
)
from hse_doc_studio.use_cases.orgs.members import (
    AddOrgMemberUC,
    ChangeOrgRoleUC,
    LeaveOrgUC,
    ListOrgMembersUC,
    RemoveOrgMemberUC,
)
from hse_doc_studio.use_cases.orgs.orgs import (
    CreateOrgUC,
    DeleteOrgUC,
    GetOrgUC,
    ListAccountOrgsUC,
    ListMyOrgsUC,
    UpdateOrgUC,
)

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.identity import InMemoryIdentityStore, InMemoryInstanceSettingsRepository, InMemoryUserRepository
from tests.fakes.orgs import InMemoryGroupRepository, InMemoryOrgRepository, InMemoryOrgStore
from tests.unit.use_cases.identity.conftest import FakeUow

T0 = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


@dataclass
class OrgWorld:
    store: InMemoryOrgStore
    users: InMemoryUserRepository
    orgs: InMemoryOrgRepository
    groups: InMemoryGroupRepository
    settings: InMemoryInstanceSettingsRepository
    audit: InMemoryAuditLog
    uow: FakeUow

    async def user(self, uid: str, *, admin: bool = False, status: UserStatus = UserStatus.active) -> Actor:
        email = f"{uid}@example.org"
        await self.users.add(
            User(
                id=uid,
                email=email,
                email_normalized=normalize_email(email),
                name=uid.title(),
                status=status,
                created_at=T0 + timedelta(seconds=self.store.tick()),
                email_verified=True,
                is_instance_admin=admin,
            )
        )
        return Actor.user(uid, uid.title(), email, is_instance_admin=admin)

    async def org(self, slug: str, **roles: OrgRole) -> str:
        """Организация с участниками `имя=роль`; пользователи создаются на лету. Возвращает id организации."""
        org = Org(id=f"org_{slug}", slug=slug, name=slug.title(), created_at=T0)
        await self.orgs.add(org)
        for uid, role in roles.items():
            if uid not in self.store.users.users:
                await self.user(uid)
            await self.orgs.add_member(OrgMember(org.id, uid, role, T0 + timedelta(seconds=self.store.tick())))
        return org.id

    def uc[T](self, kind: type[T]) -> T:
        o, u, g, a, w = self.orgs, self.users, self.groups, self.audit, self.uow
        builders = {
            ListMyOrgsUC: lambda: ListMyOrgsUC(o),
            GetOrgUC: lambda: GetOrgUC(o),
            ListAccountOrgsUC: lambda: ListAccountOrgsUC(o, g),
            CreateOrgUC: lambda: CreateOrgUC(o, u, self.settings, a, w, clock=lambda: T0),
            UpdateOrgUC: lambda: UpdateOrgUC(o, a, w),
            DeleteOrgUC: lambda: DeleteOrgUC(o, a, w),
            ListOrgMembersUC: lambda: ListOrgMembersUC(o),
            AddOrgMemberUC: lambda: AddOrgMemberUC(o, u, a, w, clock=lambda: T0),
            ChangeOrgRoleUC: lambda: ChangeOrgRoleUC(o, u, a, w),
            RemoveOrgMemberUC: lambda: RemoveOrgMemberUC(o, g, a, w),
            LeaveOrgUC: lambda: LeaveOrgUC(o, g, a, w),
            ListGroupsUC: lambda: ListGroupsUC(o, g),
            CreateGroupUC: lambda: CreateGroupUC(o, g, a, w, clock=lambda: T0),
            UpdateGroupUC: lambda: UpdateGroupUC(o, g, a, w),
            DeleteGroupUC: lambda: DeleteGroupUC(o, g, a, w),
            ListGroupMembersUC: lambda: ListGroupMembersUC(o, g),
            AddGroupMemberUC: lambda: AddGroupMemberUC(o, g, a, w),
            RemoveGroupMemberUC: lambda: RemoveGroupMemberUC(o, g, a, w),
        }
        return builders[kind]()  # type: ignore[no-any-return,index]


@pytest.fixture
def world() -> OrgWorld:
    store = InMemoryOrgStore(InMemoryIdentityStore())
    return OrgWorld(
        store=store,
        users=InMemoryUserRepository(store.users),
        orgs=InMemoryOrgRepository(store),
        groups=InMemoryGroupRepository(store),
        settings=InMemoryInstanceSettingsRepository(),
        audit=InMemoryAuditLog(),
        uow=FakeUow(),
    )
