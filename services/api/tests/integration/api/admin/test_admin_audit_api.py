"""`/api/admin/audit`: чтение журнала и покрытие аудитом всех изменяющих маршрутов админки."""

from __future__ import annotations

import json
from typing import Any

import pytest
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.identity.entities import UserStatus

from tests.integration.api.admin import test_admin_users_api as users_api
from tests.integration.api.admin.test_admin_users_api import _Env

env = users_api.env


async def test__audit__admin_reads_pages_with_keyset_and_filters(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    for n in range(5):
        await env.audit.record(f"auth.login{n}", actor_id="anna", target="t")
    await env.audit.record("admin.user_enabled", actor_id="boss", target="anna", details={"token": "hse_x"})
    client = env.make()

    first = (await client.get("/api/admin/audit?limit=4", headers=boss)).json()
    second = (await client.get(f"/api/admin/audit?limit=4&cursor={first['next_cursor']}", headers=boss)).json()
    admin_only = (await client.get("/api/admin/audit?action=admin.", headers=boss)).json()
    by_actor = (await client.get("/api/admin/audit?actor_id=anna&limit=200", headers=boss)).json()

    assert [e["action"] for e in first["items"]] == ["admin.user_enabled", "auth.login4", "auth.login3", "auth.login2"]
    assert [e["action"] for e in second["items"]] == ["auth.login1", "auth.login0"]
    assert second["next_cursor"] is None
    assert [e["details"] for e in admin_only["items"]] == [{"token": "[redacted]"}]
    assert len(by_actor["items"]) == 5


async def test__audit__page_exactly_full_has_no_next_cursor(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    await env.audit.record("a.one", actor_id=None)
    await env.audit.record("a.two", actor_id=None)
    client = env.make()

    page = (await client.get("/api/admin/audit?limit=2", headers=boss)).json()

    assert (len(page["items"]), page["next_cursor"]) == (2, None)


async def test__audit__bad_params_are_422_and_response_is_not_cached(env: _Env) -> None:
    boss = await env.add("boss", admin=True)
    client = env.make()

    for query in ("limit=0", "limit=201", "cursor=abc", "cursor=-1", "since=yesterday"):
        assert (await client.get(f"/api/admin/audit?{query}", headers=boss)).status_code == 422, query
    ok = await client.get("/api/admin/audit", headers=boss)
    assert ok.headers["cache-control"] == "no-store"


async def test__audit__student_gets_404_and_anonymous_401_and_nothing_is_writable(env: _Env) -> None:
    student = await env.add("student")
    boss = await env.add("boss", admin=True)
    client = env.make()

    assert (await client.get("/api/admin/audit", headers=student)).status_code == 404
    assert (await client.get("/api/admin/audit")).status_code == 401
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert (await client.request(method, "/api/admin/audit", headers=boss)).status_code == 405


# (метод, путь, тело, ожидаемые действия в журнале). Новая изменяющая ручка админки без строки здесь
# роняет test__audit__every_mutating_admin_route_is_in_the_matrix.
_MUTATIONS: list[tuple[str, str, Any, list[str]]] = [
    ("PATCH", "/api/admin/users/anna", {"is_instance_admin": True}, ["admin.admin_granted"]),
    ("POST", "/api/admin/users/anna/disable", None, ["admin.user_disabled"]),
    ("POST", "/api/admin/users/dora/enable", None, ["admin.user_enabled"]),
    ("POST", "/api/admin/users/anna/sessions/revoke", None, ["admin.sessions_revoked"]),
    ("POST", "/api/admin/users/anna/reset-link", {"confirm": True}, ["admin.reset_link_issued"]),
    ("POST", "/api/admin/approvals/maria/approve", None, ["admin.user_approved"]),
    ("POST", "/api/admin/approvals/pavel/reject", None, ["admin.user_rejected"]),
    ("POST", "/api/admin/invitations", {"email": "new@example.org", "ttl_days": 3}, ["invite.create"]),
]

# Ручки настроек: их проверяет test_admin_settings_api, здесь только покрытие аудитом по списку.
_SETTINGS_MUTATIONS = {
    ("PUT", "/api/admin/settings/registration"),
    ("PUT", "/api/admin/settings/auth"),
    ("PUT", "/api/admin/settings/smtp"),
    ("POST", "/api/admin/settings/smtp/test"),
    ("POST", "/api/admin/oidc-providers"),
    ("PATCH", "/api/admin/oidc-providers/{id}"),
    ("DELETE", "/api/admin/oidc-providers/{id}"),
}


def _mutating_routes() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for route in make_admin_router().routes:
        for method in getattr(route, "methods", None) or ():
            if method not in {"GET", "HEAD", "OPTIONS"}:
                found.add((method, route.path))  # type: ignore[attr-defined]
    return found


def _normalized(path: str) -> str:
    parts = path.split("/")
    return "/".join("{id}" if p.startswith("{") else p for p in parts)


async def _seed(env: _Env) -> dict[str, str]:
    boss = await env.add("boss", admin=True)
    await env.add("anna")
    await env.add("dora", status=UserStatus.disabled)
    await env.add("maria", status=UserStatus.pending_approval)
    await env.add("pavel", status=UserStatus.pending_approval)
    return boss


@pytest.mark.parametrize(
    ("method", "path", "body", "expected"), _MUTATIONS, ids=[f"{m} {p}" for m, p, _, _ in _MUTATIONS]
)
async def test__audit__each_admin_mutation_writes_exactly_its_events(
    env: _Env, method: str, path: str, body: Any, expected: list[str]
) -> None:
    boss = await _seed(env)
    client = env.make()

    response = await client.request(method, path, json=body, headers=boss)

    assert response.status_code < 300, response.text
    events = await env.audit.list()
    assert [e.action for e in reversed(events)] == expected
    assert all(e.actor_id == "boss" for e in events)
    _assert_no_link_secrets(response, events)


async def test__audit__invitation_resend_and_revoke_are_audited(env: _Env) -> None:
    boss = await _seed(env)
    client = env.make()
    created = (await client.post("/api/admin/invitations", json={"email": None, "ttl_days": 3}, headers=boss)).json()
    invite_id = created["invitation"]["id"]

    resent = await client.post(f"/api/admin/invitations/{invite_id}/resend", headers=boss)
    deleted = await client.delete(f"/api/admin/invitations/{resent.json()['invitation']['id']}", headers=boss)

    assert deleted.status_code == 204
    assert [e.action for e in reversed(await env.audit.list())] == [
        "invite.create",
        "invite.create",
        "admin.invite_resent",
        "invite.revoke",
    ]
    _assert_no_link_secrets(resent, await env.audit.list())


async def test__audit__refused_mutations_write_nothing(env: _Env) -> None:
    boss = await _seed(env)
    client = env.make()

    last = await client.patch("/api/admin/users/boss", json={"is_instance_admin": False}, headers=boss)
    missing = await client.post("/api/admin/users/ghost/disable", headers=boss)
    unconfirmed = await client.post("/api/admin/users/anna/reset-link", json={"confirm": False}, headers=boss)

    assert (last.status_code, missing.status_code, unconfirmed.status_code) == (409, 404, 403)
    assert await env.audit.list() == []


def test__audit__every_mutating_admin_route_is_in_the_matrix() -> None:
    covered = {(m, _normalized(p)) for m, p, _, _ in _MUTATIONS}
    covered |= {("POST", "/api/admin/invitations/{id}/resend"), ("DELETE", "/api/admin/invitations/{id}")}
    covered |= _SETTINGS_MUTATIONS
    routes = {(m, _normalized(p)) for m, p in _mutating_routes()}

    assert routes - covered == set(), "изменяющая ручка админки без проверки аудита"


def _assert_no_link_secrets(response: Any, events: list[Any]) -> None:
    body = response.json() if response.content else {}
    link = body.get("link") if isinstance(body, dict) else None
    if not link:
        return
    secret = link.rstrip("/").rsplit("/", 1)[-1]
    assert secret
    assert all(secret not in json.dumps(dict(e.details)) + str(e.target) for e in events)
