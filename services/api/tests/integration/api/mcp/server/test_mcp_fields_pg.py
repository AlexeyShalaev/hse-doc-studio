"""list_project_fields и удаление ключей set_project_meta в облаке: права на проект и вид работы."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import pytest

from tests.integration.api.mcp.server.test_mcp_server_pg import _call, _enable, _rpc, _token
from tests.integration.api.personal.conftest import Person, Stand

pytestmark = pytest.mark.pg

_TEMPLATE = {"pack_id": "hse-cs-sse", "template_id": "coursework", "version": "2026.1.2", "kind": "project"}


def _created_id(result: dict[str, Any]) -> str:
    assert result["isError"] is False, result
    match = re.search(r"id ([0-9a-f-]{36})", result["content"][0]["text"])
    assert match is not None, result
    return match.group(1)


def _fields(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    assert result["isError"] is False, result
    return {f["key"]: f for f in json.loads(result["content"][0]["text"])["fields"]}


async def _member(stand: Stand, project_id: str, person: Person, role: str) -> None:
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    async with stand.sessions.use() as db:
        db.add(ProjectMemberRow(project_id=UUID(project_id), principal_kind="user", principal_id=person.id, role=role))


async def test__list_project_fields__owner_and_reader_see_fields_stranger_does_not(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("fiona")
    reader = await stand.person("felix")
    stranger = await stand.person("fanny")
    owner_headers = _token(stand, owner.email, ["mcp"])
    project_id = _created_id(_call(stand, owner_headers, "create_project", {"name": "КП", **_TEMPLATE}))
    await _member(stand, project_id, reader, "reader")

    tools = {t["name"] for t in _rpc(stand, owner_headers, "tools/list").json()["result"]["tools"]}
    own = _fields(_call(stand, owner_headers, "list_project_fields", {"project_id": project_id}))
    read = _fields(
        _call(stand, _token(stand, reader.email, ["mcp"]), "list_project_fields", {"project_id": project_id})
    )
    foreign = _call(stand, _token(stand, stranger.email, ["mcp"]), "list_project_fields", {"project_id": project_id})

    assert "list_project_fields" in tools
    assert [d["id"] for d in own["udc"]["printed_in"]] == ["report"]
    assert own["udc"]["required_at"] == "finalize"
    assert read.keys() == own.keys()
    assert foreign["isError"] is True
    assert foreign["_meta"]["code"] == "not_found"


async def test__set_project_meta__unset__owner_removes_editor_forbidden(stand: Stand) -> None:
    _enable(stand)
    owner = await stand.person("frida")
    editor = await stand.person("fedya")
    owner_headers = _token(stand, owner.email, ["mcp"])
    project_id = _created_id(_call(stand, owner_headers, "create_project", {"name": "КП", **_TEMPLATE}))
    await _member(stand, project_id, editor, "editor")
    added = _call(stand, owner_headers, "set_project_meta", {"project_id": project_id, "entries": {"udc": "004.4"}})
    assert added["isError"] is False, added

    denied = _call(
        stand, _token(stand, editor.email, ["mcp"]), "set_project_meta", {"project_id": project_id, "unset": ["udc"]}
    )
    kept = _fields(_call(stand, owner_headers, "list_project_fields", {"project_id": project_id}))
    removed = _call(stand, owner_headers, "set_project_meta", {"project_id": project_id, "unset": ["udc"]})
    after = _fields(_call(stand, owner_headers, "list_project_fields", {"project_id": project_id}))

    assert denied["isError"] is True
    assert denied["_meta"]["code"] == "forbidden"
    assert kept["udc"]["value"] == "004.4"
    assert removed["isError"] is False, removed
    assert after["udc"]["value"] is None
