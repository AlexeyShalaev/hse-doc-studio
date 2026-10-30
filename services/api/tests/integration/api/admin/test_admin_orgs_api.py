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
from hse_doc_studio.api.schemas.admin_install import AdminBuildSettings, AdminInstanceSettings
from hse_doc_studio.api.schemas.session import AdminGroup, AdminOrg, AdminOrgMember
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
    AddAdminMemberUC,
    CreateAdminGroupUC,
    CreateAdminOrgUC,
    DeleteAdminGroupUC,
    DeleteAdminOrgUC,
    GetAdminOrgUC,
    ListAdminGroupsUC,
    ListAdminMembersUC,
    ListAdminOrgsUC,
    RemoveAdminMemberUC,
    SetAdminMemberRoleUC,
    UpdateAdminGroupUC,
)
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
    env = InstanceEnvOverrides(
        public_url="https://studio.hse.example", build_timeout_s=900, personal_runners_enabled=True
    )
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
    assert [AdminOrg.model_validate(x).slug for x in listed.json()] == ["msp-2026"]
    assert AdminOrgMember.model_validate(added.json()).role == "member"
    assert promoted.json()["role"] == "admin"
    assert AdminGroup.model_validate(group.json()).member_ids == ["anna"]
    assert edited.json() == {"id": gid, "name": "Команда", "member_ids": ["anna"]}
    assert (await c.get(f"{_ORG}/msp-2026/members", headers=boss)).json()[0]["role"] == "owner"
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
    assert build["fields"]["runners.personal_enabled"] == {"source": "env", "locked": True}
    locked_personal = await c.put("/api/admin/settings/build", json={"personal_runners_enabled": False}, headers=boss)
    assert (locked_personal.status_code, locked_personal.json()["code"]) == (409, "setting_locked")


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
    personal = await c.put(
        "/api/admin/settings/build",
        json={"personal_runner_wait_s": 0, "personal_runners_max_per_user": 3},
        headers=boss,
    )
    assert (personal.json()["personal_runner_wait_s"], personal.json()["personal_runners_max_per_user"]) == (0, 3)
    out_of_range = await c.put("/api/admin/settings/build", json={"personal_runner_wait_s": 61}, headers=boss)
    assert out_of_range.status_code == 422
    assert "settings.personal_runners_update" in [e.action for e in await stack.users.audit.list()]
