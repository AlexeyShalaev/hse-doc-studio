"""Организации: создание только админом (или по настройке), роли, чужая организация, удаление с проектами."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.use_cases.orgs.groups import CreateGroupUC
from hse_doc_studio.use_cases.orgs.orgs import (
    KEY_USERS_CREATE_ORGS,
    CreateOrgUC,
    DeleteOrgUC,
    GetOrgUC,
    ListMyOrgsUC,
    UpdateOrgUC,
)

from tests.unit.use_cases.orgs.conftest import OrgWorld

OWN, ADM, MEM = OrgRole.owner, OrgRole.admin, OrgRole.member


async def _code(coro: object) -> IdentityErrorCode:
    with pytest.raises(IdentityError) as caught:
        await coro  # type: ignore[misc]
    return caught.value.code


async def test__create__admin_becomes_owner_and_audit_is_written(world: OrgWorld) -> None:
    boss = await world.user("boss", admin=True)

    created = await world.uc(CreateOrgUC).execute(boss, slug="msp-2025", name="  МСПИН   2025 ")

    assert (created.org.slug, created.org.name, created.my_role) == ("msp-2025", "МСПИН 2025", OWN)
    assert (await world.uc(GetOrgUC).execute(boss, "msp-2025")).member_count == 1
    assert [e.action for e in await world.audit.list()] == ["org.create"]


async def test__create__ordinary_user_is_refused_until_the_setting_allows_it(world: OrgWorld) -> None:
    anna = await world.user("anna")

    assert await _code(world.uc(CreateOrgUC).execute(anna, slug="lab", name="Lab")) is IdentityErrorCode.forbidden
    await world.settings.set(KEY_USERS_CREATE_ORGS, True, source="test")
    created = await world.uc(CreateOrgUC).execute(anna, slug="lab", name="Lab")

    assert created.my_role is OWN


async def test__create__ordinary_user_cannot_name_another_owner(world: OrgWorld) -> None:
    anna = await world.user("anna")
    await world.user("boris")
    await world.settings.set(KEY_USERS_CREATE_ORGS, True, source="test")

    code = await _code(world.uc(CreateOrgUC).execute(anna, slug="lab", name="Lab", owner_email="boris@example.org"))

    assert code is IdentityErrorCode.forbidden


async def test__create__admin_names_another_person_as_the_owner(world: OrgWorld) -> None:
    boss = await world.user("boss", admin=True)
    boris = await world.user("boris")

    await world.uc(CreateOrgUC).execute(boss, slug="lab", name="Lab", owner_email="BORIS@example.org")

    assert [x.org.slug for x in await world.uc(ListMyOrgsUC).execute(boris)] == ["lab"]
    assert await world.uc(ListMyOrgsUC).execute(boss) == []


async def test__create__unknown_or_disabled_owner(world: OrgWorld) -> None:
    boss = await world.user("boss", admin=True)
    await world.user("gone", status=UserStatus.disabled)

    for email in ("nobody@example.org", "gone@example.org"):
        code = await _code(world.uc(CreateOrgUC).execute(boss, slug="lab", name="Lab", owner_email=email))
        assert code is IdentityErrorCode.user_not_found


@pytest.mark.parametrize(
    ("slug", "code"),
    [
        ("Bad Slug", IdentityErrorCode.slug_invalid),
        ("-lead", IdentityErrorCode.slug_invalid),
        ("", IdentityErrorCode.slug_invalid),
        ("admin", IdentityErrorCode.slug_reserved),
        ("orgs", IdentityErrorCode.slug_reserved),
    ],
)
async def test__create__slug_is_checked(world: OrgWorld, slug: str, code: IdentityErrorCode) -> None:
    boss = await world.user("boss", admin=True)

    assert await _code(world.uc(CreateOrgUC).execute(boss, slug=slug, name="X")) is code


async def test__create__slug_is_lowercased_and_unique(world: OrgWorld) -> None:
    boss = await world.user("boss", admin=True)
    await world.uc(CreateOrgUC).execute(boss, slug=" Lab ", name="Lab")

    assert (await world.uc(GetOrgUC).execute(boss, "lab")).org.slug == "lab"
    assert await _code(world.uc(CreateOrgUC).execute(boss, slug="LAB", name="Other")) is IdentityErrorCode.slug_taken


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
async def test__create__name_is_checked(world: OrgWorld, name: str) -> None:
    boss = await world.user("boss", admin=True)

    assert await _code(world.uc(CreateOrgUC).execute(boss, slug="lab", name=name)) is IdentityErrorCode.input_invalid


async def test__get__non_member_gets_not_found_even_for_an_instance_admin(world: OrgWorld) -> None:
    await world.org("lab", anna=OWN)
    boss = await world.user("boss", admin=True)
    stranger = await world.user("stranger")

    for actor in (boss, stranger):
        assert await _code(world.uc(GetOrgUC).execute(actor, "lab")) is IdentityErrorCode.not_found
    assert await _code(world.uc(GetOrgUC).execute(stranger, "missing")) is IdentityErrorCode.not_found


async def test__list__only_my_organisations_with_counters(world: OrgWorld) -> None:
    org_id = await world.org("lab", anna=OWN, boris=MEM)
    await world.org("other", boris=OWN)
    world.store.projects[org_id] = 3

    mine = await world.uc(ListMyOrgsUC).execute(await world.user("carol"))
    anna = await world.uc(ListMyOrgsUC).execute(world_actor(world, "anna"))

    assert mine == []
    assert [(x.org.slug, x.my_role, x.member_count, x.project_count) for x in anna] == [("lab", OWN, 2, 3)]


def world_actor(_world: OrgWorld, uid: str) -> Actor:
    return Actor.user(uid)


@pytest.mark.parametrize(
    ("role", "allowed"), [(OWN, True), (ADM, True), (MEM, False)], ids=["owner", "admin", "member"]
)
async def test__rename__matrix(world: OrgWorld, role: OrgRole, allowed: bool) -> None:
    await world.org("lab", pat=role, anna=OWN)

    run = world.uc(UpdateOrgUC).execute(world_actor(world, "pat"), "lab", name="Новое имя")

    if allowed:
        assert (await run).org.name == "Новое имя"
    else:
        assert await _code(run) is IdentityErrorCode.forbidden


@pytest.mark.parametrize(
    ("role", "allowed"), [(OWN, True), (ADM, False), (MEM, False)], ids=["owner", "admin", "member"]
)
async def test__delete__matrix(world: OrgWorld, role: OrgRole, allowed: bool) -> None:
    await world.org("lab", pat=role, anna=OWN)

    run = world.uc(DeleteOrgUC).execute(world_actor(world, "pat"), "lab")

    if allowed:
        await run
        assert await world.orgs.get_by_slug("lab") is None
    else:
        assert await _code(run) is IdentityErrorCode.forbidden
        assert await world.orgs.get_by_slug("lab") is not None


async def test__delete__refused_while_the_organisation_has_projects(world: OrgWorld) -> None:
    org_id = await world.org("lab", anna=OWN)
    world.store.projects[org_id] = 1

    code = await _code(world.uc(DeleteOrgUC).execute(world_actor(world, "anna"), "lab"))

    assert code is IdentityErrorCode.org_has_projects
    assert await world.orgs.get_by_slug("lab") is not None


async def test__delete__removes_members_and_groups(world: OrgWorld) -> None:
    org_id = await world.org("lab", anna=OWN, boris=MEM)
    anna = world_actor(world, "anna")
    await world.uc(CreateGroupUC).execute(anna, "lab", name="Команда")

    await world.uc(DeleteOrgUC).execute(anna, "lab")

    assert await world.orgs.list_members(org_id) == []
    assert world.store.groups == {}
