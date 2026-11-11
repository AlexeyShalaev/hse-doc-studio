"""MCP облака: токен с областью `mcp`, включение админом, права и журнал (docs/design/mcp.md, разделы 3 и 7)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from hse_doc_studio.core.mail.journal import MailCause, MailLogEntry, MailParams, MailStatus
from hse_doc_studio.infra.db.repositories.mail_log import SqlMailLogRepository

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

    # Без Bearer и с cookie запрос не проходит: CSRF-защита отвечает 403 раньше, сам `/mcp` ответил бы 401.
    assert resp.status_code in {401, 403}


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


async def test__admin_list_mail_log__compact_rows_filtered_by_recipient(stand: Stand) -> None:
    log = SqlMailLogRepository(stand.sessions)
    for email in ("Anna@Example.org", "boris@example.org"):
        await log.add(
            MailLogEntry(
                at=datetime.now(UTC),
                duration_ms=3,
                template="invite",
                lang="ru",
                to_email=email,
                subject="Приглашение в Студию",
                status=MailStatus.failed,
                reason="recipient_refused",
                smtp_code=550,
                error_text="550 mailbox unavailable",
                cause=MailCause.system,
                origin="admin_invite",
                params=MailParams(),
                template_digest="0000000000000000",
            )
        )
    _enable(stand, disabled_groups=[])
    headers = _token(stand, "stand-admin@example.org", ["mcp", "mcp:admin"])

    result = _call(
        stand,
        headers,
        "admin_list_mail_log",
        {"recipient": "anna@example.org", "status": "failed", "since": "2020-01-01", "limit": 50},
    )

    assert result["isError"] is False, result
    (row,) = json.loads(result["content"][0]["text"])
    assert (row["to"], row["status"], row["reason"], row["smtp_code"]) == (
        "Anna@Example.org",
        "failed",
        "recipient_refused",
        550,
    )
    assert (row["cause"], row["actor_id"]) == ("system", None)
    assert "mailbox unavailable" not in result["content"][0]["text"]


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


async def test__admin_settings__change__is_audited(stand: Stand) -> None:
    _enable(stand)

    events = stand.admin().get("/api/admin/audit", params={"action": "settings.mcp_update"}).json()

    assert events["items"][0]["action"] == "settings.mcp_update"


_TEMPLATE = {"pack_id": "hse-cs-se", "template_id": "vkr", "version": "2026.1"}


def _created_id(result: dict[str, Any]) -> str:
    assert result["isError"] is False, result
    match = re.search(r"id ([0-9a-f-]{36})", result["content"][0]["text"])
    assert match is not None, result
    return match.group(1)


async def test__tools_list__server__create_project_without_folder_and_no_clone(stand: Stand) -> None:
    _enable(stand)
    person = await stand.person("zoya")
    headers = _token(stand, person.email, ["mcp"])

    tools = {t["name"]: t for t in _rpc(stand, headers, "tools/list").json()["result"]["tools"]}

    schema = tools["create_project"]["inputSchema"]
    assert "folder" not in schema["properties"]
    assert "folder" not in schema["required"]
    assert "ask_user" not in tools["create_project"]["description"]
    assert "clone_cloud_project" not in tools
    assert "set_project_people" in tools


@pytest.mark.parametrize("folder", [None, "", " ", "/home/anna/vkr"])
async def test__call_tool__create_project__server_picks_the_folder(stand: Stand, folder: str | None) -> None:
    _enable(stand)
    person = await stand.person("yan")
    headers = _token(stand, person.email, ["mcp"])
    args: dict[str, Any] = {"name": "ВКР через MCP", **_TEMPLATE}
    if folder is not None:
        args["folder"] = folder

    project_id = _created_id(_call(stand, headers, "create_project", args))

    found = _call(stand, headers, "get_project", {"project_id": project_id})
    assert found["isError"] is False, found
    assert "ВКР через MCP" in found["content"][0]["text"]


async def test__call_tool__set_project_people__owner_changes_and_audit_records(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("xenia")
    headers = _token(stand, owner.email, ["mcp"])
    project_id = _created_id(_call(stand, headers, "create_project", {"name": "Курсовая", **_TEMPLATE}))

    result = _call(
        stand,
        headers,
        "set_project_people",
        {
            "project_id": project_id,
            "supervisor": {"name": "Петров П. П.", "title": "доцент", "degree": "канд. техн. наук"},
            "authors": [{"name": "Ксения Иванова", "group": "БПИ221"}],
        },
    )

    assert result["isError"] is False, result
    card = json.loads(_call(stand, headers, "get_project", {"project_id": project_id})["content"][0]["text"])
    assert card["supervisor"]["degree"] == "канд. техн. наук"
    assert [(a["name"], a["group"]) for a in card["authors"]] == [("Ксения Иванова", "БПИ221")]
    events = stand.admin().get("/api/admin/audit", params={"action": "project.people_update"}).json()["items"]
    (event,) = [e for e in events if e["target"] == project_id]
    assert event["actor_id"] == owner.id
    assert event["details"]["fields"] == ["supervisor", "authors"]
    assert event["details"]["via"] == "mcp"


async def test__call_tool__set_project_people__reader__forbidden(stand: Stand) -> None:
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    _enable(stand)
    owner = await stand.person("walter")
    reader = await stand.person("wanda")
    project_id = _created_id(
        _call(stand, _token(stand, owner.email, ["mcp"]), "create_project", {"name": "Общий", **_TEMPLATE})
    )
    async with stand.sessions.use() as db:
        db.add(
            ProjectMemberRow(project_id=UUID(project_id), principal_kind="user", principal_id=reader.id, role="reader")
        )
    headers = _token(stand, reader.email, ["mcp"])

    result = _call(stand, headers, "set_project_people", {"project_id": project_id, "supervisor": {"name": "Чужой"}})

    assert result["isError"] is True
    assert result["_meta"]["code"] == "forbidden"
    events = stand.admin().get("/api/admin/audit", params={"action": "project.people_update"}).json()["items"]
    assert not [e for e in events if e["target"] == project_id]


def _variant(stand: Stand, headers: dict[str, str], project_id: str, **extra: str) -> dict[str, Any]:
    return _call(stand, headers, "set_document_variant", {"project_id": project_id, "doc_id": "presentation", **extra})


async def test__call_tool__set_document_variant__owner_switches_and_audit_records(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("vasilisa")
    headers = _token(stand, owner.email, ["mcp"])
    project_id = _created_id(_call(stand, headers, "create_project", {"name": "Защита", **_TEMPLATE}))

    shown = _variant(stand, headers, project_id)
    switched = _variant(stand, headers, project_id, variant="beamer")

    assert shown["isError"] is False, shown
    assert {"pptx", "beamer"} <= {v["id"] for v in json.loads(shown["content"][0]["text"])["variants"]}
    assert switched["isError"] is False, switched
    assert json.loads(switched["content"][0]["text"])["variant"] == "beamer"
    events = stand.admin().get("/api/admin/audit", params={"action": "document.variant_update"}).json()["items"]
    (event,) = [e for e in events if e["target"] == project_id]
    assert event["actor_id"] == owner.id
    assert (event["details"]["doc_id"], event["details"]["after"]) == ("presentation", "beamer")


@pytest.mark.parametrize("role", ["reader", "reviewer"])
async def test__call_tool__set_document_variant__without_write_right__forbidden(stand: Stand, role: str) -> None:
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    _enable(stand)
    owner = await stand.person(f"owner-{role}")
    member = await stand.person(f"member-{role}")
    owner_headers = _token(stand, owner.email, ["mcp"])
    project_id = _created_id(_call(stand, owner_headers, "create_project", {"name": "Общий", **_TEMPLATE}))
    async with stand.sessions.use() as db:
        db.add(ProjectMemberRow(project_id=UUID(project_id), principal_kind="user", principal_id=member.id, role=role))
    before = json.loads(_variant(stand, owner_headers, project_id)["content"][0]["text"])["variant"]

    result = _variant(stand, _token(stand, member.email, ["mcp"]), project_id, variant="beamer")

    assert result["isError"] is True
    assert result["_meta"]["code"] == "forbidden"
    assert json.loads(_variant(stand, owner_headers, project_id)["content"][0]["text"])["variant"] == before
    events = stand.admin().get("/api/admin/audit", params={"action": "document.variant_update"}).json()["items"]
    assert not [e for e in events if e["target"] == project_id]
