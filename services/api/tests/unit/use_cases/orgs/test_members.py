"""Участники организации: матрица ролей, защита последнего владельца, выход, чистка групп."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.use_cases.orgs.groups import AddGroupMemberUC, CreateGroupUC, ListGroupMembersUC
from hse_doc_studio.use_cases.orgs.members import (
    AddOrgMemberUC,
    ChangeOrgRoleUC,
    LeaveOrgUC,
    ListOrgMembersUC,
    RemoveOrgMemberUC,
)

from tests.unit.use_cases.orgs.conftest import OrgWorld

OWN, ADM, MEM = OrgRole.owner, OrgRole.admin, OrgRole.member
ROLES = [OWN, ADM, MEM]


async def _code(coro: object) -> IdentityErrorCode:
    with pytest.raises(IdentityError) as caught:
        await coro  # type: ignore[misc]
    return caught.value.code


def _who(uid: str) -> Actor:
    return Actor.user(uid)


async def _role_of(world: OrgWorld, org_id: str, uid: str) -> OrgRole | None:
    member = await world.orgs.get_member(org_id, uid)
    return member.role if member else None


@pytest.mark.parametrize("actor_role", ROLES, ids=lambda r: r.value)
@pytest.mark.parametrize("new_role", ROLES, ids=lambda r: f"adds-{r.value}")
async def test__add_member__role_matrix(world: OrgWorld, actor_role: OrgRole, new_role: OrgRole) -> None:
    org_id = await world.org("lab", actor=actor_role, boss=OWN)
    await world.user("newbie")
    allowed = actor_role is OWN or (actor_role is ADM and new_role is MEM)

    run = world.uc(AddOrgMemberUC).execute(_who("actor"), "lab", email="newbie@example.org", role=new_role)

    if allowed:
        assert (await run).member.role is new_role
        assert await _role_of(world, org_id, "newbie") is new_role
    else:
        assert await _code(run) is IdentityErrorCode.forbidden
        assert await _role_of(world, org_id, "newbie") is None


async def test__add_member__plain_member_is_refused(world: OrgWorld) -> None:
    await world.org("lab", pat=MEM, boss=OWN)
    await world.user("newbie")

    code = await _code(world.uc(AddOrgMemberUC).execute(_who("pat"), "lab", email="newbie@example.org", role=MEM))

    assert code is IdentityErrorCode.forbidden


async def test__add_member__unknown_duplicate_and_foreign(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN, pat=MEM)
    await world.user("stranger")
    add = world.uc(AddOrgMemberUC)

    assert (
        await _code(add.execute(_who("boss"), "lab", email="who@example.org", role=MEM))
        is IdentityErrorCode.user_not_found
    )
    assert (
        await _code(add.execute(_who("boss"), "lab", email="pat@example.org", role=MEM))
        is IdentityErrorCode.already_member
    )
    assert (
        await _code(add.execute(_who("stranger"), "lab", email="boss@example.org", role=MEM))
        is IdentityErrorCode.not_found
    )


async def test__add_member__email_is_matched_ignoring_case(world: OrgWorld) -> None:
    org_id = await world.org("lab", boss=OWN)
    await world.user("newbie")

    await world.uc(AddOrgMemberUC).execute(_who("boss"), "lab", email=" Newbie@Example.ORG ", role=MEM)

    assert await _role_of(world, org_id, "newbie") is MEM


async def test__members__non_member_gets_not_found_and_member_sees_the_list(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN, pat=MEM)
    await world.user("stranger")

    seen = await world.uc(ListOrgMembersUC).execute(_who("pat"), "lab")

    assert [(v.member.user_id, v.member.role, v.email) for v in seen] == [
        ("boss", OWN, "boss@example.org"),
        ("pat", MEM, "pat@example.org"),
    ]
    assert await _code(world.uc(ListOrgMembersUC).execute(_who("stranger"), "lab")) is IdentityErrorCode.not_found


@pytest.mark.parametrize("actor_role", ROLES, ids=lambda r: r.value)
@pytest.mark.parametrize("target_role", ROLES, ids=lambda r: f"target-{r.value}")
@pytest.mark.parametrize("new_role", ROLES, ids=lambda r: f"to-{r.value}")
async def test__change_role__matrix(
    world: OrgWorld, actor_role: OrgRole, target_role: OrgRole, new_role: OrgRole
) -> None:
    org_id = await world.org("lab", actor=actor_role, target=target_role, other=OWN)
    expected = actor_role is OWN or (actor_role is ADM and target_role is MEM and new_role is MEM)

    run = world.uc(ChangeOrgRoleUC).execute(_who("actor"), "lab", "target", role=new_role)

    if actor_role is MEM:
        assert await _code(run) is IdentityErrorCode.forbidden
    elif expected:
        assert (await run).member.role is new_role
        assert await _role_of(world, org_id, "target") is new_role
    else:
        assert await _code(run) is IdentityErrorCode.forbidden
        assert await _role_of(world, org_id, "target") is target_role


async def test__change_role__last_owner_cannot_be_demoted_but_can_once_there_is_another(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN, pat=ADM)
    change = world.uc(ChangeOrgRoleUC)

    assert await _code(change.execute(_who("boss"), "lab", "boss", role=ADM)) is IdentityErrorCode.last_owner
    await change.execute(_who("boss"), "lab", "pat", role=OWN)
    demoted = await change.execute(_who("boss"), "lab", "boss", role=ADM)

    assert demoted.member.role is ADM


async def test__change_role__unknown_member_is_not_found(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN)
    await world.user("stranger")

    code = await _code(world.uc(ChangeOrgRoleUC).execute(_who("boss"), "lab", "stranger", role=ADM))

    assert code is IdentityErrorCode.not_found


@pytest.mark.parametrize("actor_role", ROLES, ids=lambda r: r.value)
@pytest.mark.parametrize("target_role", ROLES, ids=lambda r: f"target-{r.value}")
async def test__remove_member__matrix(world: OrgWorld, actor_role: OrgRole, target_role: OrgRole) -> None:
    org_id = await world.org("lab", actor=actor_role, target=target_role, other=OWN)
    allowed = actor_role is OWN or (actor_role is ADM and target_role is MEM)

    run = world.uc(RemoveOrgMemberUC).execute(_who("actor"), "lab", "target")

    if allowed:
        await run
        assert await _role_of(world, org_id, "target") is None
    else:
        assert await _code(run) is IdentityErrorCode.forbidden
        assert await _role_of(world, org_id, "target") is target_role


@pytest.mark.parametrize("role", ROLES, ids=lambda r: r.value)
async def test__remove_member__anyone_can_remove_themselves_unless_last_owner(world: OrgWorld, role: OrgRole) -> None:
    org_id = await world.org("lab", pat=role, other=OWN)

    await world.uc(RemoveOrgMemberUC).execute(_who("pat"), "lab", "pat")

    assert await _role_of(world, org_id, "pat") is None


async def test__leave__last_owner_cannot_leave_and_nothing_changes(world: OrgWorld) -> None:
    org_id = await world.org("lab", boss=OWN, pat=ADM)

    assert await _code(world.uc(LeaveOrgUC).execute(_who("boss"), "lab")) is IdentityErrorCode.last_owner
    assert await _code(world.uc(RemoveOrgMemberUC).execute(_who("boss"), "lab", "boss")) is IdentityErrorCode.last_owner

    assert await _role_of(world, org_id, "boss") is OWN
    assert [e.action for e in await world.audit.list()] == []


async def test__leave__second_owner_may_leave_and_is_audited(world: OrgWorld) -> None:
    org_id = await world.org("lab", boss=OWN, co=OWN)

    await world.uc(LeaveOrgUC).execute(_who("co"), "lab")

    assert await _role_of(world, org_id, "co") is None
    assert [e.action for e in await world.audit.list()] == ["org.member.leave"]


async def test__leave__non_member_gets_not_found(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN)
    await world.user("stranger")

    assert await _code(world.uc(LeaveOrgUC).execute(_who("stranger"), "lab")) is IdentityErrorCode.not_found


async def test__leaving_the_organisation_removes_group_memberships(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN, pat=MEM)
    await world.org("other", pat=OWN)
    boss = _who("boss")
    mine = await world.uc(CreateGroupUC).execute(boss, "lab", name="Команда")
    await world.uc(AddGroupMemberUC).execute(boss, mine.group.id, user_id="pat")
    theirs = await world.uc(CreateGroupUC).execute(_who("pat"), "other", name="Команда")
    await world.uc(AddGroupMemberUC).execute(_who("pat"), theirs.group.id, user_id="pat")

    await world.uc(RemoveOrgMemberUC).execute(boss, "lab", "pat")

    assert await world.uc(ListGroupMembersUC).execute(boss, mine.group.id) == []
    assert [m.user_id for m in await world.uc(ListGroupMembersUC).execute(_who("pat"), theirs.group.id)] == ["pat"]
