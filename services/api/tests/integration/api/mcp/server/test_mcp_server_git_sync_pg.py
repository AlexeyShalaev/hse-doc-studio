"""git_sync в MCP облака: синхронизация с git-remote есть и на сервере (та же кнопка), права как у POST /git/sync."""

from __future__ import annotations

from uuid import UUID

import pytest

from tests.integration.api.mcp.server.test_mcp_server_pg import _TEMPLATE, _call, _created_id, _enable, _rpc, _token
from tests.integration.api.personal.conftest import Stand

pytestmark = pytest.mark.pg


async def _project_with_reader(stand: Stand, owner_name: str, reader_name: str) -> tuple[str, dict[str, str], str]:
    """Проект владельца через MCP и читатель в нём: (project_id, заголовки владельца, почта читателя)."""
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    owner = await stand.person(owner_name)
    reader = await stand.person(reader_name)
    owner_headers = _token(stand, owner.email, ["mcp"])
    project_id = _created_id(_call(stand, owner_headers, "create_project", {"name": "Синхронизация", **_TEMPLATE}))
    async with stand.sessions.use() as db:
        db.add(
            ProjectMemberRow(project_id=UUID(project_id), principal_kind="user", principal_id=reader.id, role="reader")
        )
    return project_id, owner_headers, reader.email


async def test__tools_list__git_sync__offered_once_enabled_by_name(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=["git_sync"])
    person = await stand.person("sync-viewer")
    headers = _token(stand, person.email, ["mcp"])

    tools = {t["name"]: t for t in _rpc(stand, headers, "tools/list").json()["result"]["tools"]}

    assert set(tools["git_sync"]["inputSchema"]["properties"]) == {"project_id", "wait_s"}
    assert "clone_cloud_project" not in tools


async def test__call_tool__git_sync__reader__forbidden(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=["git_sync"])
    project_id, _, reader_email = await _project_with_reader(stand, "sync-owner", "sync-reader")
    reader = _token(stand, reader_email, ["mcp"])

    result = _call(stand, reader, "git_sync", {"project_id": project_id, "wait_s": 0})

    assert result["isError"] is True
    assert result["_meta"]["code"] == "forbidden"


async def test__call_tool__git_sync__owner_without_remote__explains(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=["git_sync"])
    project_id, owner, _ = await _project_with_reader(stand, "sync-owner2", "sync-reader2")

    result = _call(stand, owner, "git_sync", {"project_id": project_id, "wait_s": 0})

    assert result["isError"] is True
    assert result["content"][0]["text"] == "Удалённый репозиторий не подключён"
