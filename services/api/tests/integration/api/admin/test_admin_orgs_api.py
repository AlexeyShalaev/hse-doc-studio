"""`/api/admin/orgs*` и `/api/admin/settings/instance|build` по HTTP: форма ответов (эталоны), 404 не админу, коды."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.api.schemas.admin import PickerList
from hse_doc_studio.api.schemas.admin_install import AdminBuildSettings, AdminInstanceSettings
from hse_doc_studio.api.schemas.session import (
    AdminGroup,
    AdminGroupMemberPage,
    AdminOrg,
    AdminOrgMember,
    AdminOrgMemberFacets,
    AdminOrgMemberPage,
    AdminOrgPage,
    AdminUserOrgPage,
)
from hse_doc_studio.core.identity.instance_settings import InstanceEnvOverrides
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.admin.ops_install import (
    GetInstanceSettingsUC,
    UpdateBuildSettingsUC,
    UpdateInstanceSettingsUC,
)
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
from hse_doc_studio.use_cases.admin.users import ListUserOrgsUC, PickUsersUC
from hse_doc_studio.use_cases.identity.sessions import SessionService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.fakes.identity import InMemoryInstanceSettingsRepository
from tests.fakes.ops import NoopUow
from tests.fakes.orgs import InMemoryGroupRepository, InMemoryOrgRepository, InMemoryOrgStore
from tests.integration.api.admin.test_admin_users_api import _Env as _UsersEnv

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"


class _Stack:
    def __init__(self, env: InstanceEnvOverrides) -> None:
        self.users = _UsersEnv()
        self.orgs_store = InMemoryOrgStore(self.users.store)
        self.orgs = InMemoryOrgRepository(self.orgs_store)
        self.groups = InMemoryGroupRepository(self.orgs_store)
        self.settings = InMemoryInstanceSettingsRepository()
        self.env = env
        self.client: AsyncClient


def _const(item: object) -> Callable[[], object]:
    return lambda: item


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, s: _Stack) -> None:
        super().__init__()
        self.s = s
        o, u, g, a = s.orgs, s.users.users, s.groups, s.users.audit
        w = NoopUow()
        read = GetInstanceSettingsUC(s.settings, s.env)
        self.provided: list[object] = [
            ListAdminOrgsUC(o),
            GetAdminOrgUC(o),
            CreateAdminOrgUC(o, a, w),
            DeleteAdminOrgUC(o, a, w),
            ListAdminMembersUC(o),
            AddAdminMemberUC(o, u, a, w),
            SetAdminMemberRoleUC(o, u, a, w),
            RemoveAdminMemberUC(o, g, a, w),
            ListAdminGroupsUC(o, g),
            CreateAdminGroupUC(o, g, a, w),
            UpdateAdminGroupUC(o, g, a, w),
            DeleteAdminGroupUC(o, g, a, w),
            AdminMemberFacetsUC(o),
            PickOrgsUC(o),
            ListAdminGroupMembersUC(o, g),
            AddAdminGroupMemberUC(o, g, u, a, w),
            RemoveAdminGroupMemberUC(o, g, a, w),
            ListUserOrgsUC(u, o),
            PickUsersUC(s.users.directory),
            read,
            UpdateInstanceSettingsUC(s.settings, s.env, a, w, read),
            UpdateBuildSettingsUC(s.settings, s.env, a, w, read),
        ]
        for item in self.provided:
            self.provide(_const(item), provides=type(item))

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver(
            [SessionCookieResolver(SessionService(self.s.users.sessions, self.s.users.users)), empty_bearer_resolver()]
        )


async def _stack(monkeypatch: pytest.MonkeyPatch, env: InstanceEnvOverrides) -> AsyncIterator[_Stack]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    s = _Stack(env)
    app = FastAPI()
    app.include_router(make_admin_router())
    install_exception_handlers(app)
    container = make_async_container(_Provider(s), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test") as c:
        s.client = c
        yield s
    await container.close()


@pytest_asyncio.fixture
async def stack(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Stack]:
    async for s in _stack(monkeypatch, InstanceEnvOverrides()):
        yield s


@pytest_asyncio.fixture
async def locked_stack(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Stack]:
    env = InstanceEnvOverrides(public_url="https://studio.hse.example", build_timeout_s=900)
    async for s in _stack(monkeypatch, env):
        yield s


def _fixture(schema: str, name: str) -> Any:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


_ORG = "/api/admin/orgs"
_ROUTES: list[tuple[str, str, Any]] = [
    ("GET", _ORG, None),
    ("POST", _ORG, {"name": "Lab", "slug": "lab"}),
    ("GET", f"{_ORG}/lab", None),
    ("DELETE", f"{_ORG}/lab", None),
    ("GET", f"{_ORG}/lab/members", None),
    ("POST", f"{_ORG}/lab/members", {"email": "a@example.org", "role": "member"}),
    ("PATCH", f"{_ORG}/lab/members/anna", {"role": "admin"}),
    ("DELETE", f"{_ORG}/lab/members/anna", None),
    ("GET", f"{_ORG}/lab/groups", None),
    ("POST", f"{_ORG}/lab/groups", {"name": "G", "member_ids": []}),
    ("PATCH", f"{_ORG}/lab/groups/g1", {"name": "G", "member_ids": None}),
    ("DELETE", f"{_ORG}/lab/groups/g1", None),
    ("GET", f"{_ORG}/lab/members/facets", None),
    ("GET", f"{_ORG}/lab/groups/g1/members", None),
    ("POST", f"{_ORG}/lab/groups/g1/members/anna", None),
    ("DELETE", f"{_ORG}/lab/groups/g1/members/anna", None),
    ("GET", "/api/admin/users/anna/orgs", None),
    ("GET", "/api/admin/pickers/users", None),
    ("GET", "/api/admin/pickers/orgs", None),
    ("GET", "/api/admin/settings/instance", None),
    ("PUT", "/api/admin/settings/instance", {"name": "X", "public_url": None, "docs_url": None}),
    ("GET", "/api/admin/settings/build", None),
    ("PUT", "/api/admin/settings/build", {"timeout_s": 60, "artifact_retention_days": None}),
]


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES, ids=[f"{m} {p[10:50]}" for m, p, _ in _ROUTES])
async def test__routes__student_404_anonymous_401(stack: _Stack, method: str, path: str, body: Any) -> None:
    student = await stack.users.add("student")

    assert (await stack.client.request(method, path, json=body, headers=student)).status_code == 404
    assert (await stack.client.request(method, path, json=body)).status_code == 401
    assert await stack.users.audit.list() == []


async def test__org_lifecycle__create_members_groups_delete_with_fixture_shapes(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    await stack.users.add("anna")
    c = stack.client

    created = await c.post(_ORG, json=_fixture("CreateAdminOrgRequest", "one"), headers=boss)
    listed = await c.get(_ORG, headers=boss)
    added = await c.post(f"{_ORG}/msp-2026/members", json={"email": "anna@example.org", "role": "member"}, headers=boss)
    promoted = await c.patch(f"{_ORG}/msp-2026/members/anna", json={"role": "admin"}, headers=boss)
    group = await c.post(f"{_ORG}/msp-2026/groups", json={"name": "Bertie", "member_ids": ["anna"]}, headers=boss)
    gid = group.json()["id"]
    edited = await c.patch(f"{_ORG}/msp-2026/groups/{gid}", json={"name": "Команда", "member_ids": None}, headers=boss)

    assert created.status_code == 201
    assert AdminOrg.model_validate(created.json()).my_role == "owner"
    page = AdminOrgPage.model_validate(listed.json())
    assert ([x.slug for x in page.items], page.total, page.items[0].owner_count) == (["msp-2026"], 1, 1)
    assert AdminOrgMember.model_validate(added.json()).role == "member"
    assert promoted.json()["role"] == "admin"
    assert AdminGroup.model_validate(group.json()).member_count == 1
    assert edited.json() == {
        "id": gid,
        "name": "Команда",
        "member_count": 1,
        "preview": [{"user_id": "anna", "name": "Anna"}],
    }
    assert (await c.get(f"{_ORG}/msp-2026/members", headers=boss)).json()["items"][0]["role"] == "owner"
    assert (await c.delete(f"{_ORG}/msp-2026/groups/{gid}", headers=boss)).status_code == 204
    assert (await c.delete(f"{_ORG}/msp-2026/members/anna", headers=boss)).status_code == 204
    assert (await c.delete(f"{_ORG}/msp-2026", headers=boss)).status_code == 204
    assert (await c.get(f"{_ORG}/msp-2026", headers=boss)).status_code == 404
    actions = [e.action for e in await stack.users.audit.list()]
    assert {"org.create", "org.member.add", "org.member.role", "group.create", "org.delete"} <= set(actions)


async def test__errors__carry_codes_from_the_contract(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    await stack.users.add("anna")
    c = stack.client
    await c.post(_ORG, json={"name": "Lab", "slug": "lab"}, headers=boss)
    stack.orgs_store.projects[(await stack.orgs.get_by_slug("lab")).id] = 2  # type: ignore[union-attr]

    taken = await c.post(_ORG, json={"name": "Lab", "slug": "lab"}, headers=boss)
    has_projects = await c.delete(f"{_ORG}/lab", headers=boss)
    ghost = await c.post(f"{_ORG}/lab/members", json={"email": "ghost@example.org", "role": "member"}, headers=boss)
    await c.post(f"{_ORG}/lab/members", json={"email": "anna@example.org", "role": "member"}, headers=boss)
    again = await c.post(f"{_ORG}/lab/members", json={"email": "anna@example.org", "role": "member"}, headers=boss)
    last = await c.patch(f"{_ORG}/lab/members/boss", json={"role": "member"}, headers=boss)
    bad_role = await c.patch(f"{_ORG}/lab/members/anna", json={"role": "god"}, headers=boss)

    assert [(r.status_code, r.json()["code"]) for r in (taken, has_projects, ghost, again, last)] == [
        (409, "slug_taken"),
        (409, "org_has_projects"),
        (404, "user_not_found"),
        (409, "already_member"),
        (409, "last_owner"),
    ]
    assert bad_role.status_code == 422


async def test__instance_settings__defaults_update_clear_and_validate(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client

    first = (await c.get("/api/admin/settings/instance", headers=boss)).json()
    updated = await c.put(
        "/api/admin/settings/instance",
        json={"name": "Studio ВШЭ", "public_url": "https://studio.hse.example", "docs_url": "https://docs.hse.example"},
        headers=boss,
    )
    cleared = await c.put("/api/admin/settings/instance", json={"docs_url": ""}, headers=boss)
    bad_url = await c.put(
        "/api/admin/settings/instance", json={"public_url": "http://studio.example.org"}, headers=boss
    )
    bad_name = await c.put("/api/admin/settings/instance", json={"name": "   "}, headers=boss)

    shape = AdminInstanceSettings.model_validate(first)
    assert (shape.name, shape.public_url, shape.docs_url) == ("HSE Doc Studio", "", None)
    assert first["fields"] == {k: {"source": "default", "locked": False} for k in first["fields"]}
    assert updated.json()["fields"]["instance.name"] == {"source": "admin", "locked": False}
    assert cleared.json()["docs_url"] is None
    assert cleared.json()["fields"]["instance.docs_url"]["source"] == "default"
    assert (bad_url.status_code, bad_name.status_code) == (422, 422)
    assert [e.action for e in await stack.users.audit.list()] == ["settings.instance_update"] * 2


async def test__instance_settings__localhost_http_is_allowed(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)

    ok = await stack.client.put(
        "/api/admin/settings/instance", json={"public_url": "http://localhost:17240"}, headers=boss
    )

    assert ok.json()["public_url"] == "http://localhost:17240"


async def test__env_locked__keys_show_env_source_and_refuse_writes(locked_stack: _Stack) -> None:
    boss = await locked_stack.users.add("boss", admin=True)
    c = locked_stack.client

    instance = (await c.get("/api/admin/settings/instance", headers=boss)).json()
    build = (await c.get("/api/admin/settings/build", headers=boss)).json()
    refused = await c.put(
        "/api/admin/settings/instance", json={"public_url": "https://other.example", "name": "N"}, headers=boss
    )
    refused_build = await c.put("/api/admin/settings/build", json={"timeout_s": 60}, headers=boss)
    free = await c.put("/api/admin/settings/build", json={"artifact_retention_days": 7}, headers=boss)

    assert instance["public_url"] == "https://studio.hse.example"
    assert instance["fields"]["instance.public_url"] == {"source": "env", "locked": True}
    assert (build["timeout_s"], build["fields"]["build.timeout_s"]["locked"]) == (900, True)
    assert (refused.status_code, refused.json()["code"]) == (409, "setting_locked")
    assert (refused_build.status_code, refused_build.json()["code"]) == (409, "setting_locked")
    assert (await c.get("/api/admin/settings/instance", headers=boss)).json()["name"] == "HSE Doc Studio"
    assert free.json()["artifact_retention_days"] == 7


async def test__build_settings__defaults_update_and_bounds(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client

    first = (await c.get("/api/admin/settings/build", headers=boss)).json()
    updated = await c.put(
        "/api/admin/settings/build", json={"timeout_s": 120, "artifact_retention_days": 14}, headers=boss
    )
    too_small = await c.put("/api/admin/settings/build", json={"timeout_s": 10}, headers=boss)
    too_long = await c.put("/api/admin/settings/build", json={"artifact_retention_days": 400}, headers=boss)

    shape = AdminBuildSettings.model_validate(first)
    assert (shape.timeout_s, shape.artifact_retention_days) == (600, 30)
    assert (updated.json()["timeout_s"], updated.json()["artifact_retention_days"]) == (120, 14)
    assert updated.json()["fields"]["build.timeout_s"] == {"source": "admin", "locked": False}
    assert (too_small.status_code, too_long.status_code) == (422, 422)
    assert [e.action for e in await stack.users.audit.list()] == ["settings.build_update"]


async def _org_with(stack: _Stack, boss: dict[str, str], slug: str, *members: tuple[str, str]) -> None:
    c = stack.client
    assert (await c.post(_ORG, json={"name": slug.title(), "slug": slug}, headers=boss)).status_code == 201
    for uid, role in members:
        if await stack.users.users.get(uid) is None:
            await stack.users.add(uid)
        body = {"user_id": uid, "email": None, "role": role}
        assert (await c.post(f"{_ORG}/{slug}/members", json=body, headers=boss)).status_code == 201


async def test__orgs__page_search_mine_sort_and_bad_params(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    for slug in ("alpha", "beta", "gamma"):
        await _org_with(stack, boss, slug)
    await _org_with(stack, boss, "delta", ("anna", "member"), ("boris", "member"))
    delta = await stack.orgs.get_by_slug("delta")
    stack.orgs_store.members.pop((delta.id, "boss"))  # type: ignore[union-attr]

    first = AdminOrgPage.model_validate((await c.get(f"{_ORG}?limit=2", headers=boss)).json())
    second = AdminOrgPage.model_validate((await c.get(f"{_ORG}?limit=2&offset=2", headers=boss)).json())
    found = (await c.get(f"{_ORG}?q=%20ELT%20", headers=boss)).json()
    not_mine = (await c.get(f"{_ORG}?mine=false", headers=boss)).json()
    by_members = (await c.get(f"{_ORG}?sort=-member_count", headers=boss)).json()

    assert ([x.slug for x in first.items], first.total, first.limit) == (["alpha", "beta"], 4, 2)
    assert [x.slug for x in second.items] == ["delta", "gamma"]
    assert [x["slug"] for x in found["items"]] == ["delta"]
    assert [x["slug"] for x in not_mine["items"]] == ["delta"]
    assert by_members["items"][0]["slug"] == "delta"
    for bad in ("sort=owner", "sort=--name", "limit=0", "limit=201", "offset=-1", "q=" + "x" * 201):
        assert (await c.get(f"{_ORG}?{bad}", headers=boss)).status_code == 422, bad


async def test__members__page_roles_sort_facets(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    await _org_with(stack, boss, "lab", ("anna", "admin"), ("boris", "member"), ("carol", "member"))

    by_role = AdminOrgMemberPage.model_validate((await c.get(f"{_ORG}/lab/members?sort=role", headers=boss)).json())
    plain = (await c.get(f"{_ORG}/lab/members?role=member&role=admin&sort=-name&limit=2", headers=boss)).json()
    searched = (await c.get(f"{_ORG}/lab/members?q=CAROL@", headers=boss)).json()
    facets = AdminOrgMemberFacets.model_validate((await c.get(f"{_ORG}/lab/members/facets?q=o", headers=boss)).json())
    org = AdminOrg.model_validate((await c.get(f"{_ORG}/lab", headers=boss)).json())

    assert [m.user_id for m in by_role.items] == ["boss", "anna", "boris", "carol"]
    assert ([m["user_id"] for m in plain["items"]], plain["total"]) == (["carol", "boris"], 3)
    assert [m["user_id"] for m in searched["items"]] == ["carol"]
    # «o» есть в boss, boris, carol (и в адресах всех, поэтому считаются все).
    assert facets.role == {"owner": 1, "admin": 1, "member": 2}
    assert org.owner_count == 1
    assert (await c.get(f"{_ORG}/lab/members?role=god", headers=boss)).status_code == 422
    assert (await c.get(f"{_ORG}/ghost/members/facets", headers=boss)).status_code == 404


async def test__groups__page_preview_and_point_membership(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    people = [(f"p{i:02d}", "member") for i in range(7)]
    await _org_with(stack, boss, "lab", *people)
    await stack.users.add("stranger")
    big = (
        await c.post(f"{_ORG}/lab/groups", json={"name": "Big", "member_ids": [p for p, _ in people]}, headers=boss)
    ).json()
    await c.post(f"{_ORG}/lab/groups", json={"name": "Alpha", "member_ids": []}, headers=boss)

    listed = (await c.get(f"{_ORG}/lab/groups?sort=-member_count", headers=boss)).json()
    searched = (await c.get(f"{_ORG}/lab/groups?q=alp", headers=boss)).json()
    added = await c.post(f"{_ORG}/lab/groups/{big['id']}/members/boss", headers=boss)
    again = await c.post(f"{_ORG}/lab/groups/{big['id']}/members/boss", headers=boss)
    foreign = await c.post(f"{_ORG}/lab/groups/{big['id']}/members/stranger", headers=boss)
    removed = await c.delete(f"{_ORG}/lab/groups/{big['id']}/members/p00", headers=boss)
    missing = await c.delete(f"{_ORG}/lab/groups/{big['id']}/members/p00", headers=boss)
    members = AdminGroupMemberPage.model_validate(
        (await c.get(f"{_ORG}/lab/groups/{big['id']}/members?limit=3&sort=-name", headers=boss)).json()
    )
    other_org = await c.get(f"{_ORG}/ghost/groups/{big['id']}/members", headers=boss)
    # Пикер «добавить в группу» не предлагает тех, кто в ней уже есть.
    outside = (await c.get(f"{_ORG}/lab/members?not_in_group={big['id']}&sort=name", headers=boss)).json()

    assert big["member_count"] == 7
    assert [m["user_id"] for m in big["preview"]] == ["p00", "p01", "p02", "p03", "p04"]
    assert [(g["name"], g["member_count"]) for g in listed["items"]] == [("Big", 7), ("Alpha", 0)]
    assert [g["name"] for g in searched["items"]] == ["Alpha"]
    assert (added.status_code, added.json()["user_id"]) == (201, "boss")
    assert (again.status_code, foreign.status_code) == (409, 422)
    assert (removed.status_code, missing.status_code) == (204, 404)
    assert ([m.user_id for m in members.items], members.total) == (["p06", "p05", "p04"], 7)
    assert other_org.status_code == 404
    assert [m["user_id"] for m in outside["items"]] == ["p00"]
    assert [e.action for e in await stack.users.audit.list()][:2] == ["group.member.remove", "group.member.add"]


async def test__user_orgs__page_role_filter_and_unknown_user(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    await _org_with(stack, boss, "lab", ("anna", "admin"))
    await _org_with(stack, boss, "beta", ("anna", "member"))
    await _org_with(stack, boss, "zoo")

    found = AdminUserOrgPage.model_validate((await c.get("/api/admin/users/anna/orgs", headers=boss)).json())
    admins = (await c.get("/api/admin/users/anna/orgs?role=admin", headers=boss)).json()
    searched = (await c.get("/api/admin/users/anna/orgs?q=BET&sort=-joined_at", headers=boss)).json()

    assert ([(o.slug, o.role) for o in found.items], found.total) == ([("beta", "member"), ("lab", "admin")], 2)
    assert [o["slug"] for o in admins["items"]] == ["lab"]
    assert [o["slug"] for o in searched["items"]] == ["beta"]
    assert (await c.get("/api/admin/users/ghost/orgs", headers=boss)).status_code == 404


async def test__pickers__users_and_orgs_limit_has_more_and_exclusions(stack: _Stack) -> None:
    boss = await stack.users.add("boss", admin=True)
    c = stack.client
    for uid in ("anna", "annabel", "annette"):
        await stack.users.add(uid)
    await _org_with(stack, boss, "lab", ("anna", "member"))
    await _org_with(stack, boss, "lab-two")
    stack.users.directory.org_members["lab"] = {"boss", "anna"}

    first = PickerList.model_validate((await c.get("/api/admin/pickers/users?q=ANN&limit=2", headers=boss)).json())
    outside = (await c.get("/api/admin/pickers/users?q=ann&not_in_org=lab", headers=boss)).json()
    orgs = PickerList.model_validate((await c.get("/api/admin/pickers/orgs?q=lab&limit=1", headers=boss)).json())

    assert ([(i.kind, i.id, i.detail) for i in first.items], first.has_more) == (
        [("user", "anna", "anna@example.org"), ("user", "annabel", "annabel@example.org")],
        True,
    )
    assert ([i["id"] for i in outside["items"]], outside["has_more"]) == (["annabel", "annette"], False)
    assert ([(i.kind, i.id) for i in orgs.items], orgs.has_more) == ([("org", "lab")], True)
    assert (await c.get("/api/admin/pickers/users?limit=21", headers=boss)).status_code == 422
