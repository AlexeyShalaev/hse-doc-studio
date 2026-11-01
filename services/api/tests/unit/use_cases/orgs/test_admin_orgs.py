"""Организации в админке: админ установки без членства, защита последнего владельца, группы с составом."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.listing import SortKey, Window
from hse_doc_studio.core.orgs.entities import GroupMemberQuery, GroupQuery, MemberQuery, OrgQuery, OrgRole
from hse_doc_studio.use_cases.admin.orgs import (
    AddAdminGroupMemberUC,
    AddAdminMemberUC,
    AdminMemberFacetsUC,
    CreateAdminGroupUC,
    CreateAdminOrgUC,
    DeleteAdminGroupUC,
    DeleteAdminOrgUC,
    GetAdminOrgUC,
    ListAdminGroupMembersUC,
    ListAdminGroupsUC,
    ListAdminMembersUC,
    ListAdminOrgsUC,
    PickOrgsUC,
    RemoveAdminGroupMemberUC,
    RemoveAdminMemberUC,
    SetAdminMemberRoleUC,
    UpdateAdminGroupUC,
)

from tests.unit.use_cases.orgs.conftest import T0, OrgWorld

OWN, ADM, MEM = OrgRole.owner, OrgRole.admin, OrgRole.member
BOSS = Actor.user("boss", is_instance_admin=True)


async def _code(coro: object) -> IdentityErrorCode:
    with pytest.raises(IdentityError) as caught:
        await coro  # type: ignore[misc]
    return caught.value.code


class _Admin:
    def __init__(self, world: OrgWorld) -> None:
        self.w = world
        o, u, g, a, w = world.orgs, world.users, world.groups, world.audit, world.uow
        self.list = ListAdminOrgsUC(o)
        self.get = GetAdminOrgUC(o)
        self.create = CreateAdminOrgUC(o, a, w, clock=lambda: T0)
        self.delete = DeleteAdminOrgUC(o, a, w)
        self.members = ListAdminMembersUC(o)
        self.add = AddAdminMemberUC(o, u, a, w, clock=lambda: T0)
        self.role = SetAdminMemberRoleUC(o, u, a, w)
        self.remove = RemoveAdminMemberUC(o, g, a, w)
        self.groups = ListAdminGroupsUC(o, g)
        self.new_group = CreateAdminGroupUC(o, g, a, w, clock=lambda: T0)
        self.edit_group = UpdateAdminGroupUC(o, g, a, w)
        self.drop_group = DeleteAdminGroupUC(o, g, a, w)
        self.facets = AdminMemberFacetsUC(o)
        self.pick = PickOrgsUC(o)
        self.group_members = ListAdminGroupMembersUC(o, g)
        self.join_group = AddAdminGroupMemberUC(o, g, u, a, w, clock=lambda: T0)
        self.leave_group = RemoveAdminGroupMemberUC(o, g, a, w)


@pytest.fixture
async def admin(world: OrgWorld) -> _Admin:
    await world.user("boss", admin=True)
    return _Admin(world)


async def test__list__admin_sees_every_org_with_own_role_or_none(world: OrgWorld, admin: _Admin) -> None:
    await world.org("alpha", boss=ADM, anna=OWN)
    await world.org("beta", anna=OWN)
    world.store.projects["org_beta"] = 3

    found = {x.org.slug: x for x in (await admin.list.execute(BOSS, OrgQuery())).items}

    assert found["alpha"].my_role is ADM
    assert found["beta"].my_role is None
    assert (found["beta"].member_count, found["beta"].project_count) == (1, 3)


async def test__every_use_case__refuses_plain_user_as_not_found(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN)
    anna = Actor.user("anna")

    assert await _code(admin.list.execute(anna, OrgQuery())) is IdentityErrorCode.not_found
    assert await _code(admin.get.execute(anna, "lab")) is IdentityErrorCode.not_found
    assert await _code(admin.delete.execute(anna, "lab")) is IdentityErrorCode.not_found
    assert await _code(admin.remove.execute(anna, "lab", "anna")) is IdentityErrorCode.not_found


async def test__create__admin_becomes_owner_and_audit_is_written(world: OrgWorld, admin: _Admin) -> None:
    created = await admin.create.execute(BOSS, slug="Msp-2026", name="  МСПИН   2026 ")

    assert (created.org.slug, created.org.name, created.my_role) == ("msp-2026", "МСПИН 2026", OWN)
    assert [e.action for e in await world.audit.list()] == ["org.create"]


@pytest.mark.parametrize(
    ("slug", "code"),
    [("Bad Slug", IdentityErrorCode.slug_invalid), ("admin", IdentityErrorCode.slug_reserved)],
)
async def test__create__bad_slug(admin: _Admin, slug: str, code: IdentityErrorCode) -> None:
    assert await _code(admin.create.execute(BOSS, slug=slug, name="X")) is code


async def test__create__taken_slug_conflicts(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN)

    assert await _code(admin.create.execute(BOSS, slug="lab", name="Lab")) is IdentityErrorCode.slug_taken


async def test__delete__refuses_org_with_projects_then_deletes_empty(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN)
    world.store.projects["org_lab"] = 1

    assert await _code(admin.delete.execute(BOSS, "lab")) is IdentityErrorCode.org_has_projects
    world.store.projects["org_lab"] = 0
    await admin.delete.execute(BOSS, "lab")

    assert await world.orgs.get_by_slug("lab") is None


async def test__unknown_org__is_not_found(admin: _Admin) -> None:
    assert await _code(admin.members.execute(BOSS, "nope", MemberQuery())) is IdentityErrorCode.not_found


async def test__add_member__by_email_any_role_incl_owner(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN)
    await world.user("newbie")

    added = await admin.add.execute(BOSS, "lab", email="Newbie@Example.org", role=OWN)

    assert added.member.role is OWN
    assert await _code(admin.add.execute(BOSS, "lab", email="newbie@example.org", role=MEM)) is (
        IdentityErrorCode.already_member
    )
    assert await _code(admin.add.execute(BOSS, "lab", email="ghost@example.org", role=MEM)) is (
        IdentityErrorCode.user_not_found
    )


async def test__set_role__keeps_the_last_owner_and_allows_promotion(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN, boris=MEM)

    assert await _code(admin.role.execute(BOSS, "lab", "anna", role=MEM)) is IdentityErrorCode.last_owner
    promoted = await admin.role.execute(BOSS, "lab", "boris", role=OWN)
    demoted = await admin.role.execute(BOSS, "lab", "anna", role=ADM)

    assert (promoted.member.role, demoted.member.role) == (OWN, ADM)
    assert await _code(admin.role.execute(BOSS, "lab", "ghost", role=MEM)) is IdentityErrorCode.not_found


async def test__remove_member__keeps_last_owner_and_clears_groups(world: OrgWorld, admin: _Admin) -> None:
    org_id = await world.org("lab", anna=OWN, boris=MEM)
    group = await admin.new_group.execute(BOSS, "lab", name="Team", member_ids=["boris"])

    assert await _code(admin.remove.execute(BOSS, "lab", "anna")) is IdentityErrorCode.last_owner
    await admin.remove.execute(BOSS, "lab", "boris")

    assert await world.orgs.get_member(org_id, "boris") is None
    groups = (await admin.groups.execute(BOSS, "lab", GroupQuery())).items
    assert [(x.member_count, x.preview) for x in groups if x.group.id == group.group.id] == [(0, ())]


async def test__groups__create_update_delete_with_member_ids(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN, boris=MEM, carol=MEM)

    created = await admin.new_group.execute(BOSS, "lab", name=" Bertie ", member_ids=["boris", "boris", "carol"])
    renamed = await admin.edit_group.execute(BOSS, "lab", created.group.id, name="Команда", member_ids=None)
    resized = await admin.edit_group.execute(BOSS, "lab", created.group.id, name=None, member_ids=["anna", "boris"])

    def ids(view: object) -> list[str]:
        return [m.user_id for m in view.preview]  # type: ignore[attr-defined]

    assert (created.group.name, created.member_count, ids(created)) == ("Bertie", 2, ["boris", "carol"])
    assert (renamed.group.name, ids(renamed)) == ("Команда", ["boris", "carol"])
    assert (resized.group.name, ids(resized)) == ("Команда", ["anna", "boris"])
    await admin.drop_group.execute(BOSS, "lab", created.group.id)
    assert (await admin.groups.execute(BOSS, "lab", GroupQuery())).total == 0


async def test__groups__members_must_belong_to_org(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN)
    await world.user("stranger")

    code = await _code(admin.new_group.execute(BOSS, "lab", name="Team", member_ids=["stranger"]))

    assert code is IdentityErrorCode.input_invalid


async def test__groups__duplicate_name_conflicts_and_foreign_group_is_not_found(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN)
    await world.org("other", boris=OWN)
    first = await admin.new_group.execute(BOSS, "lab", name="Team", member_ids=[])
    foreign = await admin.new_group.execute(BOSS, "other", name="Team", member_ids=[])

    assert await _code(admin.new_group.execute(BOSS, "lab", name="team", member_ids=[])) is (
        IdentityErrorCode.name_taken
    )
    assert await _code(admin.edit_group.execute(BOSS, "lab", foreign.group.id, name="X", member_ids=None)) is (
        IdentityErrorCode.not_found
    )
    assert first.group.id != foreign.group.id


async def test__list__pages_searches_filters_mine_and_sorts_by_counts(world: OrgWorld, admin: _Admin) -> None:
    await world.org("alpha", boss=ADM, anna=OWN, boris=MEM)
    await world.org("beta", anna=OWN)
    await world.org("gamma", anna=OWN, boris=MEM, carol=MEM, dina=MEM)

    by_members = await admin.list.execute(BOSS, OrgQuery(sort=SortKey("member_count", descending=True)))
    mine = await admin.list.execute(BOSS, OrgQuery(mine=True))
    others = await admin.list.execute(BOSS, OrgQuery(mine=False, window=Window(limit=1)))
    found = await admin.list.execute(BOSS, OrgQuery(q="ET"))

    assert [x.org.slug for x in by_members.items] == ["gamma", "alpha", "beta"]
    assert [x.org.slug for x in mine.items] == ["alpha"]
    assert ([x.org.slug for x in others.items], others.total) == (["beta"], 2)
    assert [x.org.slug for x in found.items] == ["beta"]
    assert by_members.items[1].owner_count == 1


async def test__members__page_role_filter_sort_and_facets(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN, boris=ADM, carol=MEM, dina=MEM)

    by_role = await admin.members.execute(BOSS, "lab", MemberQuery(sort=SortKey("role")))
    plain = await admin.members.execute(BOSS, "lab", MemberQuery(roles=(MEM,), window=Window(limit=1, offset=1)))
    facets = await admin.facets.execute(BOSS, "lab", "a")

    assert [v.member.user_id for v in by_role.items] == ["anna", "boris", "carol", "dina"]
    assert ([v.member.user_id for v in plain.items], plain.total) == (["dina"], 2)
    # «a» есть в anna, carol, dina (и во всех адресах example.org), поэтому считаются все.
    assert facets == {OWN: 1, ADM: 1, MEM: 2}
    assert await admin.facets.execute(BOSS, "lab", "boris") == {OWN: 0, ADM: 1, MEM: 0}


async def test__pick_orgs__first_by_name_and_has_more(world: OrgWorld, admin: _Admin) -> None:
    for slug in ("lab-a", "lab-b", "lab-c", "zoo"):
        await world.org(slug, anna=OWN)

    found = await admin.pick.execute(BOSS, "lab", 2)

    assert ([o.slug for o in found.items], found.has_more) == (["lab-a", "lab-b"], True)
    assert await _code(admin.pick.execute(Actor.user("anna"), None, 2)) is IdentityErrorCode.not_found


async def test__group_members__point_add_remove_and_page(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN, boris=MEM, carol=MEM)
    await world.user("stranger")
    group = await admin.new_group.execute(BOSS, "lab", name="Team", member_ids=["carol"])

    added = await admin.join_group.execute(BOSS, "lab", group.group.id, "boris")
    again = await _code(admin.join_group.execute(BOSS, "lab", group.group.id, "boris"))
    foreign = await _code(admin.join_group.execute(BOSS, "lab", group.group.id, "stranger"))
    listed = await admin.group_members.execute(BOSS, "lab", group.group.id, GroupMemberQuery(q="bor"))
    await admin.leave_group.execute(BOSS, "lab", group.group.id, "carol")
    gone = await _code(admin.leave_group.execute(BOSS, "lab", group.group.id, "carol"))
    left = await admin.group_members.execute(BOSS, "lab", group.group.id, GroupMemberQuery())

    assert (added.user_id, added.name) == ("boris", "Boris")
    assert (again, foreign, gone) == (
        IdentityErrorCode.already_member,
        IdentityErrorCode.input_invalid,
        IdentityErrorCode.not_found,
    )
    assert [m.user_id for m in listed.items] == ["boris"]
    assert [m.user_id for m in left.items] == ["boris"]
    assert {"group.member.add", "group.member.remove"} <= {e.action for e in await world.audit.list()}


async def test__add_member__by_user_id(world: OrgWorld, admin: _Admin) -> None:
    await world.org("lab", anna=OWN)
    await world.user("newbie")

    added = await admin.add.execute(BOSS, "lab", user_id="newbie", role=MEM)

    assert (added.member.user_id, added.email) == ("newbie", "newbie@example.org")
    assert await _code(admin.add.execute(BOSS, "lab", user_id="ghost", role=MEM)) is IdentityErrorCode.user_not_found
