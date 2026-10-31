"""`/api/admin/audit`: чтение журнала и покрытие аудитом всех изменяющих маршрутов админки."""

from __future__ import annotations

import json
import re
from pathlib import Path
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


async def test__audit__filters_search_labels_and_opaque_cursor(env: _Env) -> None:
    boss = await env.add("boss", admin=True, name="Иван Босс")
    await env.add("anna", name="Анна Петрова")
    await env.audit.record("auth.login", actor_id="anna")
    await env.audit.record("admin.user_disabled", actor_id="boss", target="anna")
    await env.audit.record("invite.create", actor_id="boss", target="inv_1", details={"email": "new@example.org"})
    await env.audit.record("org.member.add", actor_id="deleted:abc", target="org_1", details={"slug": "lab"})
    client = env.make()

    async def actions(query: str) -> list[str]:
        response = await client.get(f"/api/admin/audit?{query}", headers=boss)
        assert response.status_code == 200, response.text
        return [e["action"] for e in response.json()["items"]]

    page = (await client.get("/api/admin/audit?limit=2", headers=boss)).json()
    rest = (await client.get(f"/api/admin/audit?limit=2&cursor={page['next_cursor']}", headers=boss)).json()
    legacy = await actions(f"limit=2&cursor={rest['items'][0]['id']}")
    filtered = (await client.get("/api/admin/audit?category=auth", headers=boss)).json()

    assert not page["next_cursor"].isdigit()
    assert [e["action"] for e in rest["items"]] == ["admin.user_disabled", "auth.login"]
    assert legacy == ["auth.login"]
    assert page["total_estimate"] == 4
    assert filtered["total_estimate"] is None
    disabled = rest["items"][0]
    assert disabled["actor"] == {"id": "boss", "name": "Иван Босс", "email": "boss@example.org"}
    assert disabled["target_label"] == "Анна Петрова"
    assert [(e["actor"], e["target_label"]) for e in page["items"]] == [
        ({"id": "deleted:abc", "name": "deleted:abc", "email": None}, "lab"),
        ({"id": "boss", "name": "Иван Босс", "email": "boss@example.org"}, "new@example.org"),
    ]
    assert await actions("category=auth&category=invite") == ["invite.create", "auth.login"]
    assert await actions("action=invite.create&action=auth.login") == ["invite.create", "auth.login"]
    assert await actions("action=admin.") == ["admin.user_disabled"]
    assert await actions("category=admin&actor_id=boss") == ["admin.user_disabled"]
    assert await actions("q=%D0%BF%D0%B5%D1%82%D1%80%D0%BE%D0%B2") == ["auth.login"]
    assert await actions("q=INV_") == ["invite.create"]
    assert await actions("target=anna") == ["admin.user_disabled"]
    assert await actions("from=2000-01-01T00:00:00Z&to=2000-01-02T00:00:00Z") == []
    assert len(await actions("since=2000-01-01T00:00:00Z")) == 4
    assert (await client.get("/api/admin/audit?category=Bad.Cat", headers=boss)).status_code == 422


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


_SETTINGS_SAMPLE = {
    "/api/admin/oidc-providers/{id}": "/api/admin/oidc-providers/x",
}
_USE_CASES = Path(__file__).resolve().parents[4] / "hse_doc_studio" / "use_cases"


def _walk_routes(router: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Все (метод, путь) роутера, включая вложенные `include_router` (в FastAPI это `_IncludedRouter`)."""
    found: list[tuple[str, str]] = []
    for route in router.routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            context = getattr(route, "include_context", None)
            found += _walk_routes(original, prefix + (getattr(context, "prefix", "") or ""))
            continue
        path = getattr(route, "path", None)
        for method in getattr(route, "methods", None) or ():
            if path is not None and method not in {"GET", "HEAD", "OPTIONS"}:
                found.append((method, prefix + path))
    return found


def _mutating_routes() -> set[tuple[str, str]]:
    return set(_walk_routes(make_admin_router()))


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


# Ручки, события которых проверяют соседние файлы (ops и orgs). Действие здесь обязано существовать в коде.
_AUDITED_ELSEWHERE: dict[tuple[str, str], str] = {
    ("DELETE", "/api/admin/users/{id}"): "admin.user_deleted",
    ("PUT", "/api/admin/settings/instance"): "settings.instance_update",
    ("PUT", "/api/admin/settings/build"): "settings.build_update",
    # links: раздел «Общий доступ» проверяет tests/integration/api/sharing
    ("PUT", "/api/admin/settings/sharing"): "settings.sharing_update",
    ("PUT", "/api/admin/settings/signing"): "settings.signing_policy_update",
    ("PUT", "/api/admin/quotas"): "settings.quotas_update",
    ("POST", "/api/admin/queue/{id}/cancel"): "queue.job_cancel",
    ("POST", "/api/admin/runner-tokens"): "runner.registration_token_create",
    ("DELETE", "/api/admin/runner-tokens/{id}"): "runner.registration_token_revoke",
    ("PATCH", "/api/admin/runners/{id}"): "runner.pause",
    ("DELETE", "/api/admin/runners/{id}"): "runner.revoke",
    ("POST", "/api/admin/runners/{id}/rotate-token"): "runner.token_rotate",
    ("POST", "/api/admin/ai-providers"): "settings.ai_provider_create",
    ("PATCH", "/api/admin/ai-providers/{id}"): "settings.ai_provider_update",
    ("DELETE", "/api/admin/ai-providers/{id}"): "settings.ai_provider_delete",
    ("POST", "/api/admin/orgs"): "org.create",
    ("DELETE", "/api/admin/orgs/{id}"): "org.delete",
    ("POST", "/api/admin/orgs/{id}/members"): "org.member.add",
    ("PATCH", "/api/admin/orgs/{id}/members/{id}"): "org.member.role",
    ("DELETE", "/api/admin/orgs/{id}/members/{id}"): "org.member.remove",
    ("POST", "/api/admin/orgs/{id}/groups"): "group.create",
    ("PATCH", "/api/admin/orgs/{id}/groups/{id}"): "group.update",
    ("DELETE", "/api/admin/orgs/{id}/groups/{id}"): "group.delete",
    ("POST", "/api/admin/orgs/{id}/groups/{id}/members/{id}"): "group.member.add",
    ("DELETE", "/api/admin/orgs/{id}/groups/{id}/members/{id}"): "group.member.remove",
}

# Изменяющие ручки без записи в журнале осознанно: только проверка соединения, состояние не меняется.
_NOT_AUDITED = {("POST", "/api/admin/ai-providers/{id}/check")}


def _matrix_covers(route: tuple[str, str], literal: set[tuple[str, str]]) -> bool:
    method, template = route
    pattern = re.compile("^" + re.sub(r"\{[^/]+\}", "[^/]+", template) + "$")
    return any(m == method and pattern.match(path) for m, path in literal)


def test__audit__every_mutating_admin_route_is_in_the_matrix() -> None:
    literal = {(m, p) for m, p, _, _ in _MUTATIONS}
    literal |= {("POST", "/api/admin/invitations/x/resend"), ("DELETE", "/api/admin/invitations/x")}
    literal |= {(m, _SETTINGS_SAMPLE.get(p, p)) for m, p in _SETTINGS_MUTATIONS}
    routes = {(m, _normalized(p)) for m, p in _mutating_routes()}

    uncovered = {
        r for r in routes if not _matrix_covers(r, literal) and r not in _AUDITED_ELSEWHERE and r not in _NOT_AUDITED
    }

    assert len(routes) > 30, "обход не нашёл маршрутов админки"
    assert uncovered == set(), "изменяющая ручка админки без проверки аудита"
    assert not (set(_AUDITED_ELSEWHERE) | _NOT_AUDITED) - routes, "в списках исключений есть несуществующая ручка"


def test__audit__elsewhere_actions_exist_in_code() -> None:
    source = "".join(p.read_text() for p in _USE_CASES.rglob("*.py"))

    missing = [a for a in _AUDITED_ELSEWHERE.values() if f'"{a}"' not in source]

    assert missing == []


def _assert_no_link_secrets(response: Any, events: list[Any]) -> None:
    body = response.json() if response.content else {}
    link = body.get("link") if isinstance(body, dict) else None
    if not link:
        return
    secret = link.rstrip("/").rsplit("/", 1)[-1]
    assert secret
    assert all(secret not in json.dumps(dict(e.details)) + str(e.target) for e in events)
