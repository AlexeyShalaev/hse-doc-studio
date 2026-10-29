"""Группы: матрица ролей, уникальность имени, состав только из участников организации, чужая группа."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.use_cases.orgs.groups import (
    AddGroupMemberUC,
    CreateGroupUC,
    DeleteGroupUC,
    ListGroupMembersUC,
    ListGroupsUC,
    RemoveGroupMemberUC,
    UpdateGroupUC,
)

from tests.unit.use_cases.orgs.conftest import OrgWorld

OWN, ADM, MEM = OrgRole.owner, OrgRole.admin, OrgRole.member


async def _code(coro: object) -> IdentityErrorCode:
    with pytest.raises(IdentityError) as caught:
        await coro  # type: ignore[misc]
    return caught.value.code


def _who(uid: str) -> Actor:
    return Actor.user(uid)


@pytest.mark.parametrize(
    ("role", "allowed"), [(OWN, True), (ADM, True), (MEM, False)], ids=["owner", "admin", "member"]
)
async def test__groups__management_matrix(world: OrgWorld, role: OrgRole, allowed: bool) -> None:
    await world.org("lab", boss=OWN, pat=role, mate=MEM)
    seed = await world.uc(CreateGroupUC).execute(_who("boss"), "lab", name="Исходная")
    gid = seed.group.id
    steps = {
        "create": lambda: world.uc(CreateGroupUC).execute(_who("pat"), "lab", name="Новая"),
        "rename": lambda: world.uc(UpdateGroupUC).execute(_who("pat"), gid, name="Другая"),
        "add": lambda: world.uc(AddGroupMemberUC).execute(_who("pat"), gid, user_id="mate"),
        "remove": lambda: world.uc(RemoveGroupMemberUC).execute(_who("pat"), gid, "boss"),
        "delete": lambda: world.uc(DeleteGroupUC).execute(_who("pat"), gid),
    }
    await world.uc(AddGroupMemberUC).execute(_who("boss"), gid, user_id="boss")

    for name, step in steps.items():
        if allowed:
            await step()
        else:
            assert await _code(step()) is IdentityErrorCode.forbidden, name


async def test__groups__every_member_reads_and_a_stranger_gets_not_found(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN, pat=MEM)
    await world.user("stranger")
    created = await world.uc(CreateGroupUC).execute(_who("boss"), "lab", name="МСПИН251")
    gid = created.group.id
    await world.uc(AddGroupMemberUC).execute(_who("boss"), gid, user_id="pat")

    groups = await world.uc(ListGroupsUC).execute(_who("pat"), "lab")
    members = await world.uc(ListGroupMembersUC).execute(_who("pat"), gid)

    assert [(g.group.name, g.member_count) for g in groups] == [("МСПИН251", 1)]
    assert [m.user_id for m in members] == ["pat"]
    assert await _code(world.uc(ListGroupsUC).execute(_who("stranger"), "lab")) is IdentityErrorCode.not_found
    assert await _code(world.uc(ListGroupMembersUC).execute(_who("stranger"), gid)) is IdentityErrorCode.not_found
    assert await _code(world.uc(DeleteGroupUC).execute(_who("stranger"), gid)) is IdentityErrorCode.not_found
    assert await _code(world.uc(ListGroupMembersUC).execute(_who("pat"), "grp_missing")) is IdentityErrorCode.not_found


async def test__groups__name_is_unique_within_the_organisation_ignoring_case(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN)
    await world.org("other", boss=OWN)
    create = world.uc(CreateGroupUC)
    first = await create.execute(_who("boss"), "lab", name="Команда")
    second = await create.execute(_who("boss"), "lab", name="Другая")

    assert await _code(create.execute(_who("boss"), "lab", name=" КОМАНДА ")) is IdentityErrorCode.name_taken
    assert (
        await _code(world.uc(UpdateGroupUC).execute(_who("boss"), second.group.id, name="команда"))
        is IdentityErrorCode.name_taken
    )
    await create.execute(_who("boss"), "other", name="Команда")
    renamed = await world.uc(UpdateGroupUC).execute(_who("boss"), first.group.id, name="Команда")

    assert renamed.group.name == "Команда"


@pytest.mark.parametrize("name", ["", "  ", "x" * 81])
async def test__groups__name_is_checked(world: OrgWorld, name: str) -> None:
    await world.org("lab", boss=OWN)

    code = await _code(world.uc(CreateGroupUC).execute(_who("boss"), "lab", name=name))

    assert code is IdentityErrorCode.input_invalid


async def test__groups__only_organisation_members_join_and_duplicates_are_refused(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN, pat=MEM)
    await world.user("stranger")
    gid = (await world.uc(CreateGroupUC).execute(_who("boss"), "lab", name="Г")).group.id
    add = world.uc(AddGroupMemberUC)

    assert await _code(add.execute(_who("boss"), gid, user_id="stranger")) is IdentityErrorCode.user_not_found
    await add.execute(_who("boss"), gid, user_id="pat")

    assert await _code(add.execute(_who("boss"), gid, user_id="pat")) is IdentityErrorCode.already_member


async def test__groups__remove_unknown_member_and_delete_clear_the_state(world: OrgWorld) -> None:
    await world.org("lab", boss=OWN, pat=MEM)
    gid = (await world.uc(CreateGroupUC).execute(_who("boss"), "lab", name="Г")).group.id
    remove = world.uc(RemoveGroupMemberUC)

    assert await _code(remove.execute(_who("boss"), gid, "pat")) is IdentityErrorCode.not_found
    await world.uc(AddGroupMemberUC).execute(_who("boss"), gid, user_id="pat")
    await remove.execute(_who("boss"), gid, "pat")
    await world.uc(AddGroupMemberUC).execute(_who("boss"), gid, user_id="pat")
    await world.uc(DeleteGroupUC).execute(_who("boss"), gid)

    assert world.store.groups == {}
    assert world.store.group_members == {}
