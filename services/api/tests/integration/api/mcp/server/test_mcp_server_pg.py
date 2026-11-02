"""MCP облака: токен с областью `mcp`, включение админом, права и журнал (docs/design/mcp.md, разделы 3 и 7)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.integration.api.personal.conftest import ORIGIN, PASSWORD, Person, Stand, seed_shared_project

pytestmark = pytest.mark.pg

_HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}


def _token(stand: Stand, email: str, scopes: list[str]) -> dict[str, str]:
    login = stand.client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN}
    )
    assert login.status_code == 200, login.text
    created = stand.client.post(
        "/api/v1/account/tokens",
        json={"name": "mcp", "scopes": scopes, "expires_in_days": 30},
        headers={"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]},
    )
    stand.client.cookies.clear()
    assert created.status_code == 201, created.text
    return {"Authorization": f"Bearer {created.json()['token']}"}


def _rpc(stand: Stand, headers: dict[str, str], method: str, params: dict[str, Any] | None = None) -> Any:
    body: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    return stand.client.post("/mcp", json=body, headers={**_HEADERS, **headers})


def _call(stand: Stand, headers: dict[str, str], name: str, args: dict[str, Any]) -> dict[str, Any]:
    resp = _rpc(stand, headers, "tools/call", {"name": name, "arguments": args})
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


def _enable(stand: Stand, **extra: object) -> None:
    resp = stand.admin().put("/api/admin/mcp/settings", json={"enabled": True, **extra})
    assert resp.status_code == 200, resp.text


async def test__mcp__no_token__answers_401_with_bearer_challenge(stand: Stand) -> None:
    resp = _rpc(stand, {}, "tools/list")

    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"].startswith("Bearer")


async def test__mcp__token_without_mcp_scope__answers_403(stand: Stand) -> None:
    person: Person = await stand.person("anna")

    resp = _rpc(stand, person.headers, "tools/list")

    assert resp.status_code == 403
    assert resp.json()["code"] == "insufficient_scope"


async def test__mcp__session_cookie__is_not_accepted(stand: Stand) -> None:
    admin = stand.admin()
    for name, value in admin.cookies.items():
        stand.client.cookies.set(name, value)
    try:
        resp = _rpc(stand, {}, "tools/list")
    finally:
        stand.client.cookies.clear()

    assert resp.status_code == 401


async def test__mcp__disabled_by_default__answers_503(stand: Stand) -> None:
    person = await stand.person("boris")
    headers = _token(stand, person.email, ["mcp"])

    resp = _rpc(stand, headers, "tools/list")

    assert resp.status_code == 503


async def test__tools_list__user__has_review_and_no_admin_tools(stand: Stand) -> None:
    _enable(stand)
    person = await stand.person("vera")
    headers = _token(stand, person.email, ["mcp"])

    tools = {t["name"] for t in _rpc(stand, headers, "tools/list").json()["result"]["tools"]}

    assert "list_review_threads" in tools
    assert not any(name.startswith("admin_") for name in tools)


async def test__call_tool__whoami__acts_as_the_token_owner(stand: Stand) -> None:
    _enable(stand)
    person = await stand.person("gleb")
    headers = _token(stand, person.email, ["mcp"])

    result = _call(stand, headers, "whoami", {})

    assert person.id in result["content"][0]["text"]


async def test__call_tool__stranger_project__answers_not_found(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("owner")
    stranger = await stand.person("stranger")
    project_id = await seed_shared_project(stand, owner)
    headers = _token(stand, stranger.email, ["mcp"])

    result = _call(stand, headers, "list_documents", {"project_id": project_id})

    assert result["isError"] is True
    assert result["_meta"]["code"] == "not_found"


async def test__call_tool__reader_cannot_write__answers_forbidden(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("owner2")
    reader = await stand.person("reader")
    project_id = await seed_shared_project(stand, owner, (reader, "reader"))
    headers = _token(stand, reader.email, ["mcp"])

    result = _call(stand, headers, "write_file", {"project_id": project_id, "path": "a.tex", "content": "x"})

    assert result["isError"] is True
    assert result["_meta"]["code"] == "forbidden"


async def test__admin_tools__need_admin_group_and_scope(stand: Stand) -> None:
    _enable(stand, disabled_groups=[])
    plain = _token(stand, "stand-admin@example.org", ["mcp"])
    full = _token(stand, "stand-admin@example.org", ["mcp", "mcp:admin"])

    hidden = _call(stand, plain, "admin_list_users", {})
    shown = _call(stand, full, "admin_list_users", {})

    assert hidden["_meta"]["code"] == "tool_disabled"
    assert shown["isError"] is False, shown
    assert "stand-admin@example.org" in shown["content"][0]["text"]


async def test__admin_tools__non_admin_with_scope__hidden(stand: Stand) -> None:
    _enable(stand, disabled_groups=[])
    person = await stand.person("dima")
    headers = _token(stand, person.email, ["mcp", "mcp:admin"])

    result = _call(stand, headers, "admin_list_users", {})

    assert result["_meta"]["code"] == "tool_disabled"


async def test__journal__admin_sees_calls(stand: Stand) -> None:
    _enable(stand)
    person = await stand.person("eva")
    headers = _token(stand, person.email, ["mcp"])
    _call(stand, headers, "whoami", {})

    calls = stand.admin().get("/api/admin/mcp/calls", params={"tool": "whoami"}).json()

    assert calls[0]["tool"] == "whoami"
    assert calls[0]["actor_id"] == person.id
    assert calls[0]["outcome"] == "ok"


async def test__admin_settings__non_admin__gets_404(stand: Stand) -> None:
    person = await stand.person("fedor")

    resp = stand.client.get("/api/admin/mcp/settings", headers=person.headers)

    assert resp.status_code == 404
