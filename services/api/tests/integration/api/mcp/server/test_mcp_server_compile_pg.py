"""compile_document в MCP облака: флаг wait в схеме, права как у кнопки «Собрать», wait=false без ожидания."""

from __future__ import annotations

import json
import re
from uuid import UUID

import pytest

from tests.integration.api.mcp.server.test_mcp_server_pg import _TEMPLATE, _call, _created_id, _enable, _rpc, _token
from tests.integration.api.personal.conftest import Stand

pytestmark = pytest.mark.pg


async def _project(stand: Stand, owner_name: str, *, runner: bool = False) -> tuple[str, dict[str, str], str]:
    """Проект через MCP: (project_id, заголовки владельца, первый документ); `runner` даёт владельцу личный раннер.

    Раннер только зарегистрирован и задания не забирает: сборка стоит в очереди, как долгая облачная сборка.
    """
    owner = await stand.person(owner_name)
    if runner:
        stand.personal_runner(owner)
    headers = _token(stand, owner.email, ["mcp"])
    project_id = _created_id(_call(stand, headers, "create_project", {"name": "Сборка", **_TEMPLATE}))
    listed = _call(stand, headers, "list_documents", {"project_id": project_id})["content"][0]["text"]
    match = re.search(r"^- ([\w-]+):", listed, re.MULTILINE)
    assert match is not None, listed
    return project_id, headers, match.group(1)


async def test__tools_list__compile_document__has_wait_flag(stand: Stand) -> None:
    _enable(stand)
    person = await stand.person("builder")
    headers = _token(stand, person.email, ["mcp"])

    tools = {t["name"]: t for t in _rpc(stand, headers, "tools/list").json()["result"]["tools"]}

    schema = tools["compile_document"]["inputSchema"]
    assert schema["required"] == ["project_id", "doc_id"]
    assert schema["properties"]["wait"] == {**schema["properties"]["wait"], "type": "boolean", "default": True}


async def test__call_tool__compile_document__wait_false__returns_compile_id_for_get_compile(stand: Stand) -> None:
    _enable(stand)
    project_id, headers, doc_id = await _project(stand, "builder-owner", runner=True)

    started = _call(stand, headers, "compile_document", {"project_id": project_id, "doc_id": doc_id, "wait": False})

    assert started["isError"] is False, started
    match = re.search(r"compile_id: ([0-9a-f-]{36})", started["content"][0]["text"])
    assert match is not None, started
    found = _call(stand, headers, "get_compile", {"project_id": project_id, "compile_id": match.group(1)})
    assert found["isError"] is False, found
    assert json.loads(found["content"][0]["text"])["id"] == match.group(1)


async def test__call_tool__compile_document__runner_build_outlives_the_wait__in_progress_not_error(
    stand: Stand, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("hse_doc_studio.use_cases.mcp.tools.compile_document.COMPILE_WAIT_S", 0.5)
    _enable(stand)
    project_id, headers, doc_id = await _project(stand, "builder-owner3", runner=True)

    result = _call(stand, headers, "compile_document", {"project_id": project_id, "doc_id": doc_id})

    assert result["isError"] is False, result
    assert "ещё идёт" in result["content"][0]["text"]
    assert "compile_id: " in result["content"][0]["text"]


async def test__call_tool__compile_document__reader__forbidden(stand: Stand) -> None:
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    _enable(stand)
    project_id, _, doc_id = await _project(stand, "builder-owner2")
    reader = await stand.person("builder-reader")
    async with stand.sessions.use() as db:
        db.add(
            ProjectMemberRow(project_id=UUID(project_id), principal_kind="user", principal_id=reader.id, role="reader")
        )

    result = _call(
        stand,
        _token(stand, reader.email, ["mcp"]),
        "compile_document",
        {"project_id": project_id, "doc_id": doc_id, "wait": False},
    )

    assert result["isError"] is True
    assert result["_meta"]["code"] == "forbidden"
