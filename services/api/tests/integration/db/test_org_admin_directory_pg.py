"""Админский список организаций, «мои организации» и панель «Доступ» в Postgres: счётчики, изоляция кандидатов."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import AccessQuery, ProjectMemberGrant
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.core.listing import SortKey, Window
from hse_doc_studio.core.orgs.entities import Group, GroupQuery, Org, OrgMember, OrgQuery, OrgRole
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.auth import SqlAuditLog
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.orgs import SqlGroupRepository, SqlOrgRepository
from hse_doc_studio.infra.db.repositories.project_directory import PostgresProjectAccessDirectory
from hse_doc_studio.infra.db.repositories.project_members import PostgresProjectMemberRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.use_cases.admin.orgs import (
    AddAdminMemberUC,
    CreateAdminGroupUC,
    CreateAdminOrgUC,
    DeleteAdminOrgUC,
    ListAdminGroupsUC,
    ListAdminOrgsUC,
    RemoveAdminMemberUC,
    UpdateAdminGroupUC,
)
from hse_doc_studio.use_cases.orgs.orgs import ListAccountOrgsUC
from hse_doc_studio.use_cases.projects.access_panel import (
    ListAccessCandidatesUC,
    ListProjectAccessUC,
    ListTransferCandidatesUC,
)

from tests.contract.test_identity_contract import make_user

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 30, tzinfo=UTC)
BOSS = Actor.user("boss", is_instance_admin=True)
OWN, ADM, MEM = OrgRole.owner, OrgRole.admin, OrgRole.member


@dataclass
class World:
    sessions: SessionProvider
    users: SqlUserRepository
    orgs: SqlOrgRepository
    groups: SqlGroupRepository
    members: PostgresProjectMemberRepository
    directory: PostgresProjectAccessDirectory
    uow: SqlUnitOfWork
    audit: SqlAuditLog

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

    async def project(self, *, owner: str | None = None, org: str | None = None) -> UUID:
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
                )
            )
        return project_id

    async def grant(self, project_id: UUID, kind: str, principal: str, role: str) -> None:
        await self.members.set_member(
            project_id,
            ProjectMemberGrant(kind, principal, Role(role)),  # type: ignore[arg-type]
        )


@pytest_asyncio.fixture
async def world(pg_migrated_engine) -> World:  # type: ignore[no-untyped-def]
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for uid in ("boss", "owner", "anna", "boris", "carol", "stranger"):
        await users.add(make_user(uid, admin=uid == "boss"))
    off = make_user("ghost")
    await users.add(off)
    return World(
        sessions,
        users,
        SqlOrgRepository(sessions),
        SqlGroupRepository(sessions),
        PostgresProjectMemberRepository(sessions),
        PostgresProjectAccessDirectory(sessions),
        SqlUnitOfWork(sessions),
        SqlAuditLog(sessions),
    )


async def test__admin_list__counts_and_viewer_role_or_none(world: World) -> None:
    alpha = await world.org("alpha", boss=ADM, anna=OWN, boris=MEM)
    await world.group(alpha, "Team", "boris")
    await world.org("beta", anna=OWN)
    await world.project(org=alpha)

    found = {x.org.slug: x for x in (await ListAdminOrgsUC(world.orgs).execute(BOSS, OrgQuery())).items}

    assert (found["alpha"].my_role, found["alpha"].member_count, found["alpha"].group_count) == (ADM, 3, 1)
    assert (found["alpha"].project_count, found["alpha"].owner_count) == (1, 1)
    assert (found["beta"].my_role, found["beta"].member_count, found["beta"].project_count) == (None, 1, 0)


async def test__admin_create_delete__owner_is_creator_and_projects_block_delete(world: World) -> None:
    created = await CreateAdminOrgUC(world.orgs, world.audit, world.uow).execute(BOSS, slug="lab", name="Lab")
    await world.project(org=created.org.id)

    from hse_doc_studio.core.identity.errors import IdentityError  # noqa: PLC0415

    with pytest.raises(IdentityError) as caught:
        await DeleteAdminOrgUC(world.orgs, world.audit, world.uow).execute(BOSS, "lab")

    assert created.my_role is OWN
    assert caught.value.code.value == "org_has_projects"


async def test__admin_groups__sync_members_in_one_call_and_removal_clears_groups(world: World) -> None:
    org_id = await world.org("lab", anna=OWN, boris=MEM, carol=MEM)
    make = CreateAdminGroupUC(world.orgs, world.groups, world.audit, world.uow)
    edit = UpdateAdminGroupUC(world.orgs, world.groups, world.audit, world.uow)
    listing = ListAdminGroupsUC(world.orgs, world.groups)

    created = await make.execute(BOSS, "lab", name="Bertie", member_ids=["boris", "carol"])
    await edit.execute(BOSS, "lab", created.group.id, name=None, member_ids=["anna", "boris"])
    await RemoveAdminMemberUC(world.orgs, world.groups, world.audit, world.uow).execute(BOSS, "lab", "boris")
    empty = await make.execute(BOSS, "lab", name="Пустая", member_ids=[])

    groups = (await listing.execute(BOSS, "lab", GroupQuery())).items
    shown = {g.group.name: [m.user_id for m in g.preview] for g in groups}
    assert shown == {"Bertie": ["anna"], "Пустая": []}
    assert (empty.member_count, empty.preview) == (0, ())
    assert await world.orgs.get_member(org_id, "boris") is None
    added = await AddAdminMemberUC(world.orgs, world.users, world.audit, world.uow).execute(
        BOSS, "lab", email="boris@example.test", role=MEM
    )
    assert added.member.role is MEM


async def test__account_orgs__roles_group_names_and_sole_owner(world: World) -> None:
    alpha = await world.org("alpha", anna=OWN, boris=MEM)
    await world.org("beta", boris=OWN, carol=OWN)
    await world.group(alpha, "Bertie", "boris")
    await world.group(alpha, "Alpha-team", "boris")
    uc = ListAccountOrgsUC(world.orgs, world.groups)

    anna = await uc.execute(Actor.user("anna"))
    boris = await uc.execute(Actor.user("boris"))

    assert [(x.summary.org.slug, x.groups, x.sole_owner) for x in anna] == [("alpha", (), True)]
    assert [(x.summary.org.slug, x.groups, x.sole_owner) for x in boris] == [
        ("alpha", ("Alpha-team", "Bertie"), False),
        ("beta", (), False),
    ]


async def test__access_list__owner_org_group_and_people_in_display_order(world: World) -> None:
    org_id = await world.org("lab", anna=OWN, boris=MEM)
    team = await world.group(org_id, "Команда", "boris")
    project = await world.project(owner="owner")
    await world.grant(project, "user", "carol", "editor")
    await world.grant(project, "user", "anna", "reader")
    await world.grant(project, "group", team, "reviewer")
    org_project = await world.project(org=org_id)

    access = ListProjectAccessUC(world.directory)
    rows = (await access.execute(project, AccessQuery())).items
    org_rows = (await access.execute(org_project, AccessQuery())).items
    by_role = (await access.execute(project, AccessQuery(sort=SortKey("role")))).items
    groups = await access.execute(project, AccessQuery(kinds=("group",)))
    readers = await access.execute(project, AccessQuery(roles=(Role.reader,), q="ANN"))
    second = await access.execute(project, AccessQuery(window=Window(limit=2, offset=2)))

    # Владелец закреплён первым, остальные по имени.
    assert [(r.subject_kind, r.subject_id, r.role.value, r.locked) for r in rows] == [
        ("user", "owner", "owner", True),
        ("user", "anna", "reader", False),
        ("user", "carol", "editor", False),
        ("group", team, "reviewer", False),
    ]
    assert rows[3].detail == "Lab"
    assert [r.subject_id for r in by_role] == ["owner", "carol", team, "anna"]
    assert ([r.subject_id for r in groups.items], groups.total) == ([team], 1)
    assert [r.subject_id for r in readers.items] == ["anna"]
    assert ([r.subject_id for r in second.items], second.total) == (["carol", team], 4)
    assert [(r.subject_kind, r.name, r.role.value, r.locked) for r in org_rows] == [("org", "Lab", "reader", True)]


async def test__access_list__unknown_project_is_not_found(world: World) -> None:
    from hse_doc_studio.core.identity.errors import IdentityError  # noqa: PLC0415

    with pytest.raises(IdentityError):
        await ListProjectAccessUC(world.directory).execute(uuid4(), AccessQuery())


async def test__candidates__only_shared_orgs_and_known_people_never_the_whole_instance(world: World) -> None:
    lab = await world.org("lab", owner=OWN, anna=MEM)
    other = await world.org("other", stranger=OWN, boris=MEM)
    await world.group(lab, "Наша группа")
    await world.group(other, "Чужая группа")
    mine = await world.project(owner="owner")
    shared_before = await world.project(owner="owner")
    await world.grant(shared_before, "user", "carol", "reader")
    uc = ListAccessCandidatesUC(world.directory)

    found = (await uc.execute(Actor.user("owner"), mine, "")).items

    assert [(c.subject_kind, c.name) for c in found] == [("group", "Наша группа"), ("user", "Anna"), ("user", "Carol")]
    assert all(c.subject_id not in {"stranger", "boris", "ghost", "boss"} for c in found)


async def test__candidates__exclude_already_added_owner_disabled_and_filter_by_query(world: World) -> None:
    lab = await world.org("lab", owner=OWN, anna=MEM, boris=MEM, carol=MEM)
    team = await world.group(lab, "Bertie")
    await world.group(lab, "Zeta")
    project = await world.project(owner="owner")
    await world.grant(project, "user", "anna", "reader")
    await world.grant(project, "group", team, "reader")
    async with world.sessions.use() as session:
        from hse_doc_studio.infra.db.orm.identity import UserRow  # noqa: PLC0415

        row = await session.get(UserRow, "carol")
        assert row is not None
        row.status = UserStatus.disabled.value
    uc = ListAccessCandidatesUC(world.directory)

    everyone = (await uc.execute(Actor.user("owner"), project, "")).items
    by_mail = (await uc.execute(Actor.user("owner"), project, "BORIS@")).items
    by_group = (await uc.execute(Actor.user("owner"), project, "zet")).items
    percent = (await uc.execute(Actor.user("owner"), project, "%")).items
    only_people = (await uc.execute(Actor.user("owner"), project, "", kind="user")).items

    assert [(c.subject_kind, c.subject_id) for c in everyone] == [("group", "grp_Zeta"), ("user", "boris")]
    assert [c.subject_id for c in by_mail] == ["boris"]
    assert [c.subject_id for c in by_group] == ["grp_Zeta"]
    assert percent == []
    assert [c.subject_id for c in only_people] == ["boris"]


async def test__candidates__org_project_offers_only_owner_org_groups_and_people(world: World) -> None:
    lab = await world.org("lab", owner=OWN, anna=MEM)
    other = await world.org("other", owner=OWN, boris=MEM)
    await world.group(lab, "Lab-team")
    await world.group(other, "Other-team")
    project = await world.project(org=lab)

    found = (await ListAccessCandidatesUC(world.directory).execute(Actor.user("owner"), project, "")).items

    assert [(c.subject_kind, c.subject_id) for c in found] == [("group", "grp_Lab-team"), ("user", "anna")]


async def test__candidates__limit_and_deleted_project(world: World) -> None:
    lab = await world.org("lab", owner=OWN)
    for i in range(15):
        uid = f"member{i:02d}"
        await world.users.add(make_user(uid))
        await world.orgs.add_member(OrgMember(lab, uid, MEM, NOW))
    project = await world.project(owner="owner")
    uc = ListAccessCandidatesUC(world.directory)

    found = await uc.execute(Actor.user("owner"), project, "")
    small = await uc.execute(Actor.user("owner"), project, "", limit=5)
    exact = await uc.execute(Actor.user("owner"), project, "member1", limit=5)

    assert (len(found.items), found.has_more) == (15, False)
    assert (len(small.items), small.has_more) == (5, True)
    assert (len(exact.items), exact.has_more) == (5, False)
    gone = await uc.execute(Actor.user("owner"), uuid4(), "")
    assert (gone.items, gone.has_more) == ([], False)


async def test__transfer_candidates__managed_orgs_then_people_of_shared_orgs(world: World) -> None:
    lab = await world.org("lab", owner=OWN, anna=MEM)
    await world.org("club", owner=ADM, boris=MEM)
    await world.org("plain", owner=MEM, carol=MEM)
    await world.org("other", stranger=OWN)
    project = await world.project(owner="owner")
    org_project = await world.project(org=lab)
    uc = ListTransferCandidatesUC(world.directory)

    found = await uc.execute(Actor.user("owner"), project, "")
    from_org = await uc.execute(Actor.user("owner"), org_project, "", kind="org")
    people = await uc.execute(Actor.user("owner"), project, "A", kind="user", limit=1)

    assert [(c.kind, c.id) for c in found.items] == [
        ("org", "club"),
        ("org", "lab"),
        ("user", "anna"),
        ("user", "boris"),
        ("user", "carol"),
    ]
    assert [c.id for c in from_org.items] == ["club"]
    assert ([c.id for c in people.items], people.has_more) == (["anna"], True)
    assert all(c.id not in {"stranger", "other", "owner"} for c in found.items)
