"""MCP облака: подпись комплекта только с отдельным правом токена `sign` (docs/design/signature-plan.md, 9)."""

from __future__ import annotations

import pytest

from tests.integration.api.mcp.server.test_mcp_server_pg import _call, _enable, _rpc, _token
from tests.integration.api.personal.conftest import Stand, seed_shared_project

pytestmark = pytest.mark.pg


def _tool_names(stand: Stand, headers: dict[str, str]) -> set[str]:
    resp = _rpc(stand, headers, "tools/list")
    assert resp.status_code == 200, resp.text
    return {tool["name"] for tool in resp.json()["result"]["tools"]}


async def test__sign_submission__token_without_sign_scope__hidden_and_forbidden(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=["sign_submission"])
    owner = await stand.person("signer")
    project_id = await seed_shared_project(stand, owner)
    headers = _token(stand, owner.email, ["mcp"])

    names = _tool_names(stand, headers)
    result = _call(stand, headers, "sign_submission", {"project_id": project_id, "profile_id": "final"})

    assert "sign_submission" not in names
    assert "get_signature_plan" in names
    assert result["isError"] is True
    assert result["_meta"]["code"] == "forbidden"


async def test__sign_submission__token_with_sign_scope__offered(stand: Stand) -> None:
    _enable(stand, enabled_dangerous=["sign_submission"])
    owner = await stand.person("signer2")
    headers = _token(stand, owner.email, ["mcp", "sign"])

    assert "sign_submission" in _tool_names(stand, headers)
