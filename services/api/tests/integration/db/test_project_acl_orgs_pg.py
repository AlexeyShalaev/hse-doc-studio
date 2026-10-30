"""Права через организации и группы в Postgres: загрузчик, список видимых проектов и назначение ролей."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.access.repositories import ProjectMemberGrant
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import Group, Org, OrgMember, OrgRole
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.repositories.auth import SqlAuditLog
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.orgs import SqlGroupRepository, SqlOrgRepository
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository
from hse_doc_studio.infra.db.repositories.project_directory import PostgresProjectAccessDirectory
from hse_doc_studio.infra.db.repositories.project_members import PostgresProjectMemberRepository
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.acl_flags import AclFlagsCache
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.use_cases.projects.members import RemoveProjectMemberUC, SetProjectMemberUC

from tests.contract.test_identity_contract import make_user

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 30, tzinfo=UTC)
USERS = ("owner", "anna", "boris", "carol", "dave")


def actor(uid: str) -> Actor:
    return Actor.user(uid)


@dataclass
class World:
    sessions: SessionProvider
    acl: PostgresProjectAclRepository
    locator: PostgresProjectLocator
    orgs: SqlOrgRepository
    groups: SqlGroupRepository
    members: PostgresProjectMemberRepository
    uow: SqlUnitOfWork
    audit: SqlAuditLog
    users: SqlUserRepository

    async def org(self, slug: str, **roles: OrgRole) -> str:
        org = Org(id=f"org_{slug}", slug=slug, name=slug.title(), created_at=NOW)
        await self.orgs.add(org)
        for uid, role in roles.items():
            await self.orgs.add_member(OrgMember(org.id, uid, role, NOW))
        return org.id

    async def group(self, org_id: str, name: str, *users: str) -> str:
        group = Group(id=f"grp_{name}", org_id=org_id, name=name, created_at=NOW)
        await self.groups.add(group)
        for uid in users:
            await self.groups.add_member(group.id, uid)
        return group.id

    async def project(self, *, owner: str | None = None, org: str | None = None, org_visible: bool = False) -> UUID:
        project_id = uuid4()
        async with self.sessions.use() as session:
            session.add(
                ProjectRow(
                    id=project_id,
                    name="P",
                    owner_user_id=owner,
                    owner_org_id=org,
                    workspace_path=str(project_id),
                    kind="report",
                    lang="ru",
                    org_visible=org_visible,
                )
            )
        return project_id

    async def grant(self, project_id: UUID, kind: str, principal: str, role: str) -> None:
        async with self.sessions.use() as session:
            session.add(ProjectMemberRow(project_id=project_id, principal_kind=kind, principal_id=principal, role=role))

    async def role_of(self, uid: str, project_id: UUID) -> Role | None:
        acl = await self.acl.load_for(actor(uid), project_id)
        grant = acl.grant_for(actor(uid)) if acl else None
        return grant.role if grant else None

    async def visible(self, uid: str) -> set[UUID]:
        return {UUID(p.name) for p in await self.locator.list_visible(actor(uid))}


@pytest_asyncio.fixture
async def world(pg_migrated_engine, tmp_path: Path) -> World:  # type: ignore[no-untyped-def]
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for uid in USERS:
        await users.add(make_user(uid))
    volume = LocalDiskProjectVolume(tmp_path / "projects")
    return World(
        sessions,
        PostgresProjectAclRepository(sessions, AclFlagsCache()),
        PostgresProjectLocator(sessions, volume, JsonProjectRepository()),
        SqlOrgRepository(sessions),
        SqlGroupRepository(sessions),
        PostgresProjectMemberRepository(sessions),
        SqlUnitOfWork(sessions),
        SqlAuditLog(sessions),
        users,
    )


def _set_uc(w: World) -> SetProjectMemberUC:
    return SetProjectMemberUC(
        w.members, w.users, w.groups, w.orgs, PostgresProjectAccessDirectory(w.sessions), w.audit, w.uow
    )


# Организация-владелец проекта: (роль в организации, org_visible, группа с ролью, прямая роль) -> итог.
_ORG_MATRIX = [
    ("owner", False, None, None, Role.owner),
    ("admin", False, None, None, Role.owner),
    ("admin", True, "reader", "reader", Role.owner),
    ("member", False, None, None, None),
    ("member", True, None, None, Role.reader),
    ("member", False, "editor", None, Role.editor),
    ("member", True, "reviewer", None, Role.reviewer),
    ("member", True, "reader", "editor", Role.editor),
    ("member", False, "editor", "reader", Role.editor),
    (None, True, None, None, None),
    (None, False, "reviewer", None, Role.reviewer),
    (None, False, None, "reader", Role.reader),
]


@pytest.mark.parametrize(("org_role", "visible", "group_role", "direct_role", "expected"), _ORG_MATRIX)
async def test__org_project__matrix__role_and_visibility_agree(
    world: World,
    org_role: str | None,
    visible: bool,
    group_role: str | None,
    direct_role: str | None,
    expected: Role | None,
) -> None:
    roles = {"owner": OrgRole.owner}
    if org_role is not None:
        roles["anna"] = OrgRole(org_role)
    org = await world.org("acme", **roles)
    pid = await world.project(org=org, org_visible=visible)
    if group_role is not None:
        gid = await world.group(org, "team", "anna")
        await world.grant(pid, "group", gid, group_role)
    if direct_role is not None:
        await world.grant(pid, "user", "anna", direct_role)

    assert await world.role_of("anna", pid) == expected
    assert (pid in await world.visible("anna")) is (expected is not None)
    found = await world.acl.memberships_for(actor("anna"), [pid])
    assert (found[pid].my_role if pid in found else None) == expected
    if pid in found:
        assert (found[pid].owner.kind, found[pid].owner.slug, found[pid].owner.name) == ("org", "acme", "Acme")


async def test__personal_project__group_does_not_demote_owner(world: World) -> None:
    org = await world.org("acme", owner=OrgRole.owner, anna=OrgRole.member)
    gid = await world.group(org, "team", "owner")
    pid = await world.project(owner="owner")
    await world.grant(pid, "group", gid, "reader")

    assert await world.role_of("owner", pid) is Role.owner


async def test__removed_from_group__access_closes_at_once(world: World) -> None:
    org = await world.org("acme", owner=OrgRole.owner, anna=OrgRole.member)
    gid = await world.group(org, "team", "anna")
    pid = await world.project(owner="owner")
    await world.grant(pid, "group", gid, "editor")
    assert await world.role_of("anna", pid) is Role.editor

    await world.groups.remove_member(gid, "anna")

    assert await world.role_of("anna", pid) is None
    assert await world.visible("anna") == set()


async def test__left_org__group_access_and_org_visibility_close(world: World) -> None:
    org = await world.org("acme", owner=OrgRole.owner, anna=OrgRole.member)
    gid = await world.group(org, "team", "anna")
    shared = await world.project(org=org, org_visible=True)
    pid = await world.project(owner="owner")
    await world.grant(pid, "group", gid, "editor")

    await world.groups.remove_user_from_org_groups(org, "anna")
    await world.orgs.remove_member(org, "anna")

    assert await world.role_of("anna", pid) is None
    assert await world.role_of("anna", shared) is None


async def test__org_admin__does_not_see_personal_projects_of_members(world: World) -> None:
    org = await world.org("acme", owner=OrgRole.owner, anna=OrgRole.admin, boris=OrgRole.member)
    pid = await world.project(owner="boris")

    assert await world.role_of("anna", pid) is None
    assert await world.visible("anna") == set()
    acl = await world.acl.load_for(actor("anna"), pid)
    assert decide(actor("anna"), Action.PROJECT_VIEW, acl) is Decision.not_found
    assert org


async def test__instance_admin__has_no_implicit_access(world: World) -> None:
    pid = await world.project(owner="owner")
    boss = Actor.user("anna", is_instance_admin=True)

    acl = await world.acl.load_for(boss, pid)

    assert acl is None


async def test__unknown_role_in_row__opens_nothing(world: World) -> None:
    pid = await world.project(owner="owner")
    await world.grant(pid, "user", "anna", "superuser")

    assert await world.role_of("anna", pid) is None


async def test__deleted_project__invisible_for_everyone(world: World) -> None:
    org = await world.org("acme", owner=OrgRole.owner)
    pid = await world.project(org=org, org_visible=True)
    async with world.sessions.use() as session:
        row = await session.get(ProjectRow, pid)
        assert row is not None
        row.deleted_at = NOW

    assert await world.role_of("owner", pid) is None
    assert await world.visible("owner") == set()


async def test__set_member__group_of_foreign_org__not_found(world: World) -> None:
    mine = await world.org("mine", owner=OrgRole.owner)
    other = await world.org("other", anna=OrgRole.owner)
    foreign = await world.group(other, "outsiders", "anna")
    own = await world.group(mine, "insiders", "boris")
    pid = await world.project(owner="owner")
    grant = ProjectMemberGrant("group", foreign, Role.editor)

    with pytest.raises(IdentityError) as exc:
        await _set_uc(world).execute(actor("owner"), pid, grant)
    assert exc.value.code is IdentityErrorCode.not_found

    view = await _set_uc(world).execute(actor("owner"), pid, ProjectMemberGrant("group", own, Role.editor))
    assert view.name == "insiders"
    assert [x.principal_id for x in await _members(world, pid)] == [own]


async def _members(world: World, pid: UUID) -> list[ProjectMemberRow]:
    from sqlalchemy import select

    async with world.sessions.use() as session:
        stmt = select(ProjectMemberRow).where(
            ProjectMemberRow.project_id == pid, ProjectMemberRow.principal_kind == "group"
        )
        return list((await session.execute(stmt)).scalars())


async def test__set_member__org_project__only_groups_of_that_org(world: World) -> None:
    mine = await world.org("mine", owner=OrgRole.owner)
    other = await world.org("other", owner=OrgRole.owner)
    foreign = await world.group(other, "outsiders", "anna")
    pid = await world.project(org=mine)

    with pytest.raises(IdentityError) as exc:
        await _set_uc(world).execute(actor("owner"), pid, ProjectMemberGrant("group", foreign, Role.reader))
    assert exc.value.code is IdentityErrorCode.not_found


async def test__set_member__user_replaces_role_and_opens_access(world: World) -> None:
    await world.org("acme", owner=OrgRole.owner, anna=OrgRole.member)
    pid = await world.project(owner="owner")
    uc = _set_uc(world)

    await uc.execute(actor("owner"), pid, ProjectMemberGrant("user", "anna", Role.reader))
    assert await world.role_of("anna", pid) is Role.reader
    await uc.execute(actor("owner"), pid, ProjectMemberGrant("user", "anna", Role.editor, persona="ivanov"))

    assert await world.role_of("anna", pid) is Role.editor
    assert await world.visible("anna") == {pid}


async def test__set_member__user_outside_the_owners_circle__not_found_like_a_missing_one(world: World) -> None:
    pid = await world.project(owner="owner")
    await world.org("elsewhere", anna=OrgRole.owner)
    uc = _set_uc(world)

    for principal in ("anna", "nobody"):
        with pytest.raises(IdentityError) as exc:
            await uc.execute(actor("owner"), pid, ProjectMemberGrant("user", principal, Role.reader))
        assert exc.value.code is IdentityErrorCode.not_found
    assert await world.role_of("anna", pid) is None


async def test__set_member__user_known_from_owners_other_project__allowed(world: World) -> None:
    first = await world.project(owner="owner")
    second = await world.project(owner="owner")
    await world.grant(first, "user", "anna", "reader")

    await _set_uc(world).execute(actor("owner"), second, ProjectMemberGrant("user", "anna", Role.reader))

    assert await world.role_of("anna", second) is Role.reader


@pytest.mark.parametrize(
    ("principal", "role"),
    [("owner", Role.reader), ("anna", Role.owner), ("nobody", Role.reader)],
)
async def test__set_member__invalid__rejected(world: World, principal: str, role: Role) -> None:
    pid = await world.project(owner="owner")

    with pytest.raises(IdentityError):
        await _set_uc(world).execute(actor("owner"), pid, ProjectMemberGrant("user", principal, role))

    assert await world.role_of("owner", pid) is Role.owner


async def test__remove_member__closes_access_and_reports_missing(world: World) -> None:
    await world.org("acme", owner=OrgRole.owner, anna=OrgRole.member)
    pid = await world.project(owner="owner")
    await _set_uc(world).execute(actor("owner"), pid, ProjectMemberGrant("user", "anna", Role.editor))
    remove = RemoveProjectMemberUC(world.members, world.audit, world.uow)

    await remove.execute(actor("owner"), pid, "user", "anna")

    assert await world.role_of("anna", pid) is None
    with pytest.raises(IdentityError) as exc:
        await remove.execute(actor("owner"), pid, "user", "anna")
    assert exc.value.code is IdentityErrorCode.not_found
    with pytest.raises(IdentityError) as owner_exc:
        await remove.execute(actor("owner"), pid, "user", "owner")
    assert owner_exc.value.code is IdentityErrorCode.input_invalid


async def test__delete_group__removes_its_grants(world: World) -> None:
    org = await world.org("acme", owner=OrgRole.owner, anna=OrgRole.member)
    gid = await world.group(org, "team", "anna")
    pid = await world.project(owner="owner")
    await world.grant(pid, "group", gid, "editor")

    await world.groups.delete(gid)

    assert await _members(world, pid) == []
    assert await world.role_of("anna", pid) is None
