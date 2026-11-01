"""`/orgs` и `/groups` по HTTP: форма ответов (эталоны), 404 чужому, 403 по роли, коды конфликтов, локальный режим."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.auth_cookie import SESSION_COOKIE
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import Session
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.orgs.entities import OrgRole
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.sessions import SessionService
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
    KEY_USERS_CREATE_ORGS,
    CreateOrgUC,
    DeleteOrgUC,
    GetOrgUC,
    ListAccountOrgsUC,
    ListMyOrgsUC,
    UpdateOrgUC,
)
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemorySessionRepository, empty_bearer_resolver
from tests.unit.use_cases.orgs.conftest import OrgWorld

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"
NOW = datetime.now(UTC)
OWN, ADM, MEM = OrgRole.owner, OrgRole.admin, OrgRole.member

_USE_CASES: list[type] = [
    ListMyOrgsUC,
    ListAccountOrgsUC,
    GetOrgUC,
    CreateOrgUC,
    UpdateOrgUC,
    DeleteOrgUC,
    ListOrgMembersUC,
    AddOrgMemberUC,
    ChangeOrgRoleUC,
    RemoveOrgMemberUC,
    LeaveOrgUC,
    ListGroupsUC,
    CreateGroupUC,
    UpdateGroupUC,
    DeleteGroupUC,
    ListGroupMembersUC,
    AddGroupMemberUC,
    RemoveGroupMemberUC,
]


class _Env:
    def __init__(self, world: OrgWorld) -> None:
        self.world = world
        self.sessions = InMemorySessionRepository()

    async def login(self, uid: str, *, admin: bool = False) -> dict[str, str]:
        if uid not in self.world.store.users.users:
            await self.world.user(uid, admin=admin)
        await self.sessions.add(Session(hash_token(f"s-{uid}"), uid, "csrf", NOW, NOW, NOW + timedelta(days=7)))
        return {"Cookie": f"{SESSION_COOKIE}=s-{uid}"}


def _provider(env: _Env) -> Provider:
    provider = Provider(scope=Scope.APP)
    resolver = ChainActorResolver(
        [SessionCookieResolver(SessionService(env.sessions, env.world.users)), empty_bearer_resolver()]
    )
    provider.provide(lambda: resolver, provides=IActorResolver)
    for kind in _USE_CASES:
        provider.provide(_builder(env.world, kind), provides=kind)
    return provider


def _builder(world: OrgWorld, kind: type) -> Callable[[], object]:
    def build() -> object:
        return world.uc(kind)

    return build


@pytest_asyncio.fixture
async def env(world: OrgWorld, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, _Env]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    e = _Env(world)
    app = FastAPI()
    app.include_router(api_router)
    install_exception_handlers(app)
    container = make_async_container(_provider(e), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, e
    await container.close()


def _fixture(name: str, variant: str) -> Any:
    return json.loads((_FIXTURES / name / f"{variant}.json").read_text(encoding="utf-8"))


async def test__orgs__responses_have_the_contract_shape(env: tuple[AsyncClient, _Env]) -> None:
    client, e = env
    boss = await e.login("boss", admin=True)
    await e.world.user("anna")
    await e.world.user("maria")

    created = await client.post("/api/v1/orgs", json=_fixture("CreateOrgRequest", "msp"), headers=boss)
    listing = await client.get("/api/v1/orgs", headers=boss)
    added = await client.post(
        "/api/v1/orgs/msp-2025/members", json=_fixture("AddOrgMemberRequest", "admin"), headers=boss
    )
    await client.post(
        "/api/v1/orgs/msp-2025/members", json={"email": "anna@example.org", "role": "member"}, headers=boss
    )
    group = await client.post("/api/v1/orgs/msp-2025/groups", json=_fixture("CreateGroupRequest", "team"), headers=boss)
    in_group = await client.post(f"/api/v1/groups/{group.json()['id']}/members", json={"user_id": "anna"}, headers=boss)

    assert created.status_code == 201
    assert set(created.json()) == set(_fixture("Org", "owner"))
    assert listing.json()[0]["slug"] == "msp-2025"
    assert set(added.json()) == set(_fixture("OrgMember", "admin"))
    assert (added.status_code, group.status_code, in_group.status_code) == (201, 201, 201)
    assert set(group.json()) == set(_fixture("Group", "team"))
    assert set(in_group.json()) == set(_fixture("GroupMember", "anna"))
    assert created.headers.get("cache-control") != "public"


async def test__orgs__anonymous_gets_401_and_a_stranger_gets_404_everywhere(env: tuple[AsyncClient, _Env]) -> None:
    client, e = env
    await e.world.org("lab", boss=OWN)
    group = await e.world.uc(CreateGroupUC).execute(Actor.user("boss"), "lab", name="Г")
    stranger = await e.login("stranger")
    gid = group.group.id
    calls = [
        ("GET", "/api/v1/orgs/lab", None),
        ("PATCH", "/api/v1/orgs/lab", {"name": "X"}),
        ("DELETE", "/api/v1/orgs/lab", None),
        ("GET", "/api/v1/orgs/lab/members", None),
        ("POST", "/api/v1/orgs/lab/members", {"email": "boss@example.org", "role": "member"}),
        ("PATCH", "/api/v1/orgs/lab/members/boss", {"role": "member"}),
        ("DELETE", "/api/v1/orgs/lab/members/boss", None),
        ("POST", "/api/v1/orgs/lab/leave", None),
        ("GET", "/api/v1/orgs/lab/groups", None),
        ("POST", "/api/v1/orgs/lab/groups", {"name": "Новая"}),
        ("PATCH", f"/api/v1/groups/{gid}", {"name": "X"}),
        ("DELETE", f"/api/v1/groups/{gid}", None),
        ("GET", f"/api/v1/groups/{gid}/members", None),
        ("POST", f"/api/v1/groups/{gid}/members", {"user_id": "boss"}),
        ("DELETE", f"/api/v1/groups/{gid}/members/boss", None),
    ]

    for method, path, body in calls:
        anonymous = await client.request(method, path, json=body)
        foreign = await client.request(method, path, json=body, headers=stranger)
        assert anonymous.status_code == 401, (method, path)
        assert foreign.status_code == 404, (method, path)
        assert foreign.json()["code"] == "not_found"


async def test__orgs__create_needs_the_admin_or_the_setting(env: tuple[AsyncClient, _Env]) -> None:
    client, e = env
    anna = await e.login("anna")
    body = {"slug": "lab", "name": "Lab", "owner_email": None}

    refused = await client.post("/api/v1/orgs", json=body, headers=anna)
    await e.world.settings.set(KEY_USERS_CREATE_ORGS, True, source="test")
    allowed = await client.post("/api/v1/orgs", json=body, headers=anna)
    taken = await client.post("/api/v1/orgs", json=body, headers=anna)

    assert (refused.status_code, refused.json()["code"]) == (403, "forbidden")
    assert allowed.status_code == 201
    assert (taken.status_code, taken.json()["code"]) == (409, "slug_taken")


@pytest.mark.parametrize(
    ("slug", "status", "code"), [("Bad Slug", 422, "slug_invalid"), ("admin", 422, "slug_reserved")]
)
async def test__orgs__bad_slug_is_a_typed_error(
    env: tuple[AsyncClient, _Env], slug: str, status: int, code: str
) -> None:
    client, e = env
    boss = await e.login("boss", admin=True)

    response = await client.post("/api/v1/orgs", json={"slug": slug, "name": "X", "owner_email": None}, headers=boss)

    assert (response.status_code, response.json()["code"]) == (status, code)


async def test__orgs__role_gates_return_403_and_last_owner_is_409(env: tuple[AsyncClient, _Env]) -> None:
    client, e = env
    await e.world.org("lab", boss=OWN, pat=MEM)
    boss, pat = await e.login("boss"), await e.login("pat")

    rename = await client.patch("/api/v1/orgs/lab", json={"name": "X"}, headers=pat)
    delete = await client.delete("/api/v1/orgs/lab", headers=pat)
    leave_last = await client.post("/api/v1/orgs/lab/leave", headers=boss)
    demote_last = await client.patch("/api/v1/orgs/lab/members/boss", json={"role": "admin"}, headers=boss)
    read = await client.get("/api/v1/orgs/lab", headers=pat)

    assert (rename.status_code, delete.status_code) == (403, 403)
    assert [(r.status_code, r.json()["code"]) for r in (leave_last, demote_last)] == [(409, "last_owner")] * 2
    assert (read.status_code, read.json()["my_role"]) == (200, "member")


async def test__orgs__delete_with_projects_is_refused_with_a_code_and_empty_org_goes_away(
    env: tuple[AsyncClient, _Env],
) -> None:
    client, e = env
    org_id = await e.world.org("lab", boss=OWN)
    boss = await e.login("boss")
    e.world.store.projects[org_id] = 2

    refused = await client.delete("/api/v1/orgs/lab", headers=boss)
    e.world.store.projects[org_id] = 0
    deleted = await client.delete("/api/v1/orgs/lab", headers=boss)

    assert (refused.status_code, refused.json()["code"]) == (409, "org_has_projects")
    assert deleted.status_code == 204
    assert (await client.get("/api/v1/orgs/lab", headers=boss)).status_code == 404


async def test__orgs__member_flow_add_change_remove_and_leave(env: tuple[AsyncClient, _Env]) -> None:
    client, e = env
    await e.world.org("lab", boss=OWN)
    await e.world.user("pat")
    boss, pat = await e.login("boss"), await e.login("pat")

    unknown = await client.post(
        "/api/v1/orgs/lab/members", json={"email": "no@example.org", "role": "member"}, headers=boss
    )
    added = await client.post(
        "/api/v1/orgs/lab/members", json={"email": "pat@example.org", "role": "member"}, headers=boss
    )
    twice = await client.post(
        "/api/v1/orgs/lab/members", json={"email": "pat@example.org", "role": "member"}, headers=boss
    )
    promoted = await client.patch("/api/v1/orgs/lab/members/pat", json={"role": "admin"}, headers=boss)
    listed = await client.get("/api/v1/orgs/lab/members", headers=pat)
    left = await client.post("/api/v1/orgs/lab/leave", headers=pat)
    after = await client.get("/api/v1/orgs/lab", headers=pat)

    assert (unknown.status_code, unknown.json()["code"]) == (404, "user_not_found")
    assert added.status_code == 201
    assert (twice.status_code, twice.json()["code"]) == (409, "already_member")
    assert promoted.json()["role"] == "admin"
    assert sorted((m["user_id"], m["role"]) for m in listed.json()) == [("boss", "owner"), ("pat", "admin")]
    assert (left.status_code, after.status_code) == (204, 404)


async def test__groups__flow_and_conflicts(env: tuple[AsyncClient, _Env]) -> None:
    client, e = env
    await e.world.org("lab", boss=OWN, pat=MEM)
    await e.world.user("outsider")
    boss = await e.login("boss")

    made = await client.post("/api/v1/orgs/lab/groups", json={"name": "Команда"}, headers=boss)
    dup = await client.post("/api/v1/orgs/lab/groups", json={"name": "команда"}, headers=boss)
    gid = made.json()["id"]
    outsider = await client.post(f"/api/v1/groups/{gid}/members", json={"user_id": "outsider"}, headers=boss)
    joined = await client.post(f"/api/v1/groups/{gid}/members", json={"user_id": "pat"}, headers=boss)
    renamed = await client.patch(f"/api/v1/groups/{gid}", json={"name": "Bertie"}, headers=boss)
    members = await client.get(f"/api/v1/groups/{gid}/members", headers=boss)
    removed = await client.delete(f"/api/v1/groups/{gid}/members/pat", headers=boss)
    listing = await client.get("/api/v1/orgs/lab/groups", headers=boss)
    deleted = await client.delete(f"/api/v1/groups/{gid}", headers=boss)

    assert (dup.status_code, dup.json()["code"]) == (409, "name_taken")
    assert (outsider.status_code, outsider.json()["code"]) == (404, "user_not_found")
    assert joined.status_code == 201
    assert (renamed.json()["name"], renamed.json()["member_count"]) == ("Bertie", 1)
    assert [m["user_id"] for m in members.json()] == ["pat"]
    assert removed.status_code == 204
    assert listing.json()[0]["member_count"] == 0
    assert deleted.status_code == 204


async def test__orgs__unknown_body_field_and_empty_name_are_rejected_before_any_use_case(
    env: tuple[AsyncClient, _Env],
) -> None:
    client, e = env
    boss = await e.login("boss", admin=True)

    surprise = await client.post(
        "/api/v1/orgs", json={"slug": "a", "name": "A", "owner_email": None, "x": 1}, headers=boss
    )
    empty = await client.post("/api/v1/orgs", json={"slug": "a", "name": "", "owner_email": None}, headers=boss)

    assert (surprise.status_code, empty.status_code) == (422, 422)


async def test__orgs__routes_do_not_exist_in_the_local_mode(
    env: tuple[AsyncClient, _Env], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = env
    monkeypatch.setattr(settings, "mode", StudioMode.local)

    assert (await client.get("/api/v1/orgs")).status_code == 404
    assert (await client.post("/api/v1/orgs", json={"slug": "a", "name": "A", "owner_email": None})).status_code == 404


async def test__account_orgs__lists_only_own_with_contract_shape_and_leave_guards_sole_owner(
    env: tuple[AsyncClient, _Env],
) -> None:
    client, e = env
    anna = await e.login("anna")
    await e.world.org("lab", anna=OWN, boris=MEM)
    await e.world.org("other", carol=OWN)
    group = await e.world.uc(CreateGroupUC).execute(Actor.user("anna"), "lab", name="Bertie")
    await e.world.uc(AddGroupMemberUC).execute(Actor.user("anna"), group.group.id, user_id="boris")
    boris = await e.login("boris")

    mine = await client.get("/api/v1/account/orgs", headers=boris)
    sole = await client.delete("/api/v1/account/orgs/lab/membership", headers=anna)
    stranger = await client.delete("/api/v1/account/orgs/other/membership", headers=anna)
    left = await client.delete("/api/v1/account/orgs/lab/membership", headers=boris)
    after = await client.get("/api/v1/account/orgs", headers=boris)

    assert set(mine.json()[0]) == set(_fixture("MyOrg", "one"))
    assert [(x["slug"], x["my_role"], x["groups"], x["sole_owner"]) for x in mine.json()] == [
        ("lab", "member", ["Bertie"], False)
    ]
    assert (sole.status_code, sole.json()["code"]) == (409, "last_owner")
    assert (stranger.status_code, stranger.json()["code"]) == (404, "not_found")
    assert (left.status_code, after.json()) == (204, [])
    assert (await client.get("/api/v1/account/orgs")).status_code == 401
