"""Организации и группы в Postgres: уникальность, каскады, блокировка владельцев, внешний ключ проектов."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import OrgMember, OrgRole
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.auth import SqlAuditLog
from hse_doc_studio.infra.db.repositories.identity import SqlInstanceSettingsRepository, SqlUserRepository
from hse_doc_studio.infra.db.repositories.orgs import SqlGroupRepository, SqlOrgRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.use_cases.orgs.groups import AddGroupMemberUC, CreateGroupUC, ListGroupMembersUC, ListGroupsUC
from hse_doc_studio.use_cases.orgs.members import AddOrgMemberUC, ChangeOrgRoleUC, LeaveOrgUC, RemoveOrgMemberUC
from hse_doc_studio.use_cases.orgs.orgs import CreateOrgUC, DeleteOrgUC, GetOrgUC
from sqlalchemy.exc import IntegrityError

from tests.contract.test_identity_contract import make_user

pytestmark = pytest.mark.pg

BOSS = Actor.user("boss", is_instance_admin=True)


@dataclass
class World:
    sessions: SessionProvider
    users: SqlUserRepository
    orgs: SqlOrgRepository
    groups: SqlGroupRepository
    uow: SqlUnitOfWork
    audit: SqlAuditLog

    def create(self) -> CreateOrgUC:
        return CreateOrgUC(self.orgs, self.users, SqlInstanceSettingsRepository(self.sessions), self.audit, self.uow)


@pytest_asyncio.fixture
async def world(pg_migrated_engine) -> World:  # type: ignore[no-untyped-def]
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for uid in ("boss", "anna", "boris", "carol"):
        await users.add(make_user(uid, admin=uid == "boss"))
    return World(
        sessions,
        users,
        SqlOrgRepository(sessions),
        SqlGroupRepository(sessions),
        SqlUnitOfWork(sessions),
        SqlAuditLog(sessions),
    )


async def test__create__owner_membership_counters_and_taken_slug(world: World) -> None:
    created = await world.create().execute(BOSS, slug="lab", name="Lab")

    shown = await GetOrgUC(world.orgs).execute(BOSS, "lab")
    with pytest.raises(IdentityError) as taken:
        await world.create().execute(BOSS, slug="lab", name="Other")

    assert (created.my_role, shown.member_count, shown.group_count, shown.project_count) == (OrgRole.owner, 1, 0, 0)
    assert shown.org.policies == {"version": 1}
    assert taken.value.code is IdentityErrorCode.slug_taken
    assert [x.org.slug for x in await world.orgs.list_for_user("boss")] == ["lab"]


async def test__create__a_failed_step_rolls_the_whole_organisation_back(world: World) -> None:
    with pytest.raises(IdentityError):
        await world.create().execute(BOSS, slug="lab", name="Lab", owner_email="nobody@example.test")

    assert await world.orgs.get_by_slug("lab") is None


async def test__members__duplicate_role_change_and_cascade_to_groups(world: World) -> None:
    await world.create().execute(BOSS, slug="lab", name="Lab")
    add = AddOrgMemberUC(world.orgs, world.users, world.audit, world.uow)
    await add.execute(BOSS, "lab", email="anna@example.test", role=OrgRole.member)
    with pytest.raises(IdentityError) as twice:
        await add.execute(BOSS, "lab", email="ANNA@example.test", role=OrgRole.member)
    group = await CreateGroupUC(world.orgs, world.groups, world.audit, world.uow).execute(BOSS, "lab", name="Команда")
    await AddGroupMemberUC(world.orgs, world.groups, world.audit, world.uow).execute(
        BOSS, group.group.id, user_id="anna"
    )
    other = await world.create().execute(BOSS, slug="other", name="Other")
    other_group = await CreateGroupUC(world.orgs, world.groups, world.audit, world.uow).execute(
        BOSS, "other", name="Команда"
    )
    await world.orgs.add_member(OrgMember(other.org.id, "anna", OrgRole.member, other.org.created_at))
    await world.groups.add_member(other_group.group.id, "anna")

    await RemoveOrgMemberUC(world.orgs, world.groups, world.audit, world.uow).execute(BOSS, "lab", "anna")

    assert twice.value.code is IdentityErrorCode.already_member
    assert await ListGroupMembersUC(world.orgs, world.groups).execute(BOSS, group.group.id) == []
    assert [m.user_id for m in await world.groups.list_members(other_group.group.id)] == ["anna"]


async def test__groups__name_unique_ignoring_case_per_organisation(world: World) -> None:
    await world.create().execute(BOSS, slug="lab", name="Lab")
    await world.create().execute(BOSS, slug="other", name="Other")
    create = CreateGroupUC(world.orgs, world.groups, world.audit, world.uow)
    await create.execute(BOSS, "lab", name="Команда")

    with pytest.raises(IdentityError) as clash:
        await create.execute(BOSS, "lab", name="КОМАНДА")
    await create.execute(BOSS, "other", name="Команда")

    assert clash.value.code is IdentityErrorCode.name_taken
    assert [
        (g.group.name, g.member_count) for g in await ListGroupsUC(world.orgs, world.groups).execute(BOSS, "lab")
    ] == [("Команда", 0)]


async def test__owners__concurrent_departures_leave_one_owner(world: World) -> None:
    await world.create().execute(BOSS, slug="lab", name="Lab")
    add = AddOrgMemberUC(world.orgs, world.users, world.audit, world.uow)
    await add.execute(BOSS, "lab", email="anna@example.test", role=OrgRole.owner)
    leave = LeaveOrgUC(world.orgs, world.groups, world.audit, world.uow)

    results = await asyncio.gather(
        leave.execute(BOSS, "lab"), leave.execute(Actor.user("anna"), "lab"), return_exceptions=True
    )

    errors = [r for r in results if isinstance(r, IdentityError)]
    assert [e.code for e in errors] == [IdentityErrorCode.last_owner]
    assert len(await world.orgs.lock_owners((await world.orgs.get_by_slug("lab")).id)) == 1  # type: ignore[union-attr]


async def test__change_role__concurrent_demotions_leave_one_owner(world: World) -> None:
    await world.create().execute(BOSS, slug="lab", name="Lab")
    await AddOrgMemberUC(world.orgs, world.users, world.audit, world.uow).execute(
        BOSS, "lab", email="anna@example.test", role=OrgRole.owner
    )
    change = ChangeOrgRoleUC(world.orgs, world.users, world.audit, world.uow)

    results = await asyncio.gather(
        change.execute(BOSS, "lab", "anna", role=OrgRole.member),
        change.execute(Actor.user("anna"), "lab", "boss", role=OrgRole.member),
        return_exceptions=True,
    )

    assert sum(isinstance(r, IdentityError) for r in results) == 1
    assert len(await world.orgs.lock_owners((await world.orgs.get_by_slug("lab")).id)) == 1  # type: ignore[union-attr]


async def test__delete__projects_block_it_in_the_use_case_and_in_the_foreign_key(world: World) -> None:
    created = await world.create().execute(BOSS, slug="lab", name="Lab")
    async with world.sessions.use() as db:
        db.add(
            ProjectRow(
                id=uuid.uuid4(), name="P", owner_org_id=created.org.id, workspace_path="/p", kind="research", lang="ru"
            )
        )

    with pytest.raises(IdentityError) as refused:
        await DeleteOrgUC(world.orgs, world.audit, world.uow).execute(BOSS, "lab")
    with pytest.raises(IntegrityError):
        await world.orgs.delete(created.org.id)

    assert refused.value.code is IdentityErrorCode.org_has_projects
    assert (await GetOrgUC(world.orgs).execute(BOSS, "lab")).project_count == 1


async def test__delete__empty_organisation_takes_members_and_groups_with_it(world: World) -> None:
    created = await world.create().execute(BOSS, slug="lab", name="Lab")
    group = await CreateGroupUC(world.orgs, world.groups, world.audit, world.uow).execute(BOSS, "lab", name="Г")
    await AddGroupMemberUC(world.orgs, world.groups, world.audit, world.uow).execute(
        BOSS, group.group.id, user_id="boss"
    )

    await DeleteOrgUC(world.orgs, world.audit, world.uow).execute(BOSS, "lab")

    assert await world.orgs.get_member(created.org.id, "boss") is None
    assert await world.groups.get(group.group.id) is None
    assert await world.groups.list_members(group.group.id) == []


async def test__lists__members_sorted_by_join_time_and_orgs_by_name(world: World) -> None:
    await world.create().execute(BOSS, slug="zeta", name="alpha")
    await world.create().execute(BOSS, slug="alpha", name="Beta")

    assert [x.org.slug for x in await world.orgs.list_for_user("boss")] == ["zeta", "alpha"]
    assert [v.email for v in await world.orgs.list_members((await world.orgs.get_by_slug("zeta")).id)] == [  # type: ignore[union-attr]
        "boss@example.test"
    ]
