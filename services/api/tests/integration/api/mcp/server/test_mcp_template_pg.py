"""MCP облака: обновление шаблона владельцем с аудитом и отказ соавтору без права TEMPLATE_MANAGE."""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from hse_doc_studio.api.config import settings

from tests.fixtures.template_pack import PACK_ID, TEMPLATE_ID, V1, V2, build_update_pack
from tests.integration.api.personal.conftest import ORIGIN, PASSWORD, Stand

pytestmark = [pytest.mark.pg, pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")]

_HEADERS = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
_TEMPLATE = {"pack_id": PACK_ID, "template_id": TEMPLATE_ID, "version": V1}


@pytest.fixture
def update_pack(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Синтетический пак с версиями 2026.1 и 2026.1.1 вместо встроенных; ставится до запуска приложения."""
    packs_dir = tmp_path_factory.mktemp("packs")
    build_update_pack(packs_dir)
    monkeypatch.setattr(settings, "packs_dir", packs_dir)
    return packs_dir


@pytest_asyncio.fixture
async def upd_stand(update_pack: Path, stand: Stand) -> AsyncIterator[Stand]:
    resp = stand.admin().put("/api/admin/mcp/settings", json={"enabled": True})
    assert resp.status_code == 200, resp.text
    yield stand


def _token(stand: Stand, email: str) -> dict[str, str]:
    login = stand.client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}, headers={"Origin": ORIGIN}
    )
    assert login.status_code == 200, login.text
    created = stand.client.post(
        "/api/v1/account/tokens",
        json={"name": "mcp", "scopes": ["mcp"], "expires_in_days": 30},
        headers={"Origin": ORIGIN, "X-CSRF-Token": login.json()["csrf_token"]},
    )
    stand.client.cookies.clear()
    assert created.status_code == 201, created.text
    return {"Authorization": f"Bearer {created.json()['token']}"}


def _call(stand: Stand, headers: dict[str, str], name: str, args: dict[str, Any]) -> dict[str, Any]:
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}}
    resp = stand.client.post("/mcp", json=body, headers={**_HEADERS, **headers})
    assert resp.status_code == 200, resp.text
    return resp.json()["result"]


def _ok(result: dict[str, Any]) -> Any:
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


def _create(stand: Stand, headers: dict[str, str]) -> str:
    result = _call(stand, headers, "create_project", {"name": "Курсовой проект", **_TEMPLATE})
    assert result["isError"] is False, result
    match = re.search(r"id ([0-9a-f-]{36})", result["content"][0]["text"])
    assert match is not None, result
    return match.group(1)


def _audit(stand: Stand, project_id: str) -> list[dict[str, Any]]:
    events = stand.admin().get("/api/admin/audit", params={"action": "project.template_update"}).json()["items"]
    return [e for e in events if e["target"] == project_id]


async def test__template_update__owner__status_plan_apply_and_audit(upd_stand: Stand) -> None:
    owner = await upd_stand.person("tamara")
    headers = _token(upd_stand, owner.email)
    project_id = _create(upd_stand, headers)

    status = _ok(_call(upd_stand, headers, "template_update_status", {"project_id": project_id}))
    plan = _ok(_call(upd_stand, headers, "plan_template_update", {"project_id": project_id, "to_version": V2}))
    applied = _ok(
        _call(
            upd_stand,
            headers,
            "apply_template_update",
            {"project_id": project_id, "to_version": V2, "fingerprint": plan["fingerprint"]},
        )
    )
    after = _ok(_call(upd_stand, headers, "template_update_status", {"project_id": project_id}))

    assert (status["current_version"], status["recommended"]["version"]) == (V1, V2)
    assert "report/appendix.tex" in applied["written"]
    assert after["current_version"] == V2
    (event,) = _audit(upd_stand, project_id)
    assert event["actor_id"] == owner.id
    assert (event["details"]["from_version"], event["details"]["to_version"]) == (V1, V2)
    assert event["details"]["via"] == "mcp"


async def test__template_update__editor__sees_status_but_cannot_plan_or_apply(upd_stand: Stand) -> None:
    from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow  # noqa: PLC0415

    owner = await upd_stand.person("timur")
    editor = await upd_stand.person("tanya")
    owner_headers = _token(upd_stand, owner.email)
    project_id = _create(upd_stand, owner_headers)
    plan = _ok(_call(upd_stand, owner_headers, "plan_template_update", {"project_id": project_id, "to_version": V2}))
    async with upd_stand.sessions.use() as db:
        db.add(
            ProjectMemberRow(project_id=UUID(project_id), principal_kind="user", principal_id=editor.id, role="editor")
        )
    headers = _token(upd_stand, editor.email)

    status = _ok(_call(upd_stand, headers, "template_update_status", {"project_id": project_id}))
    planned = _call(upd_stand, headers, "plan_template_update", {"project_id": project_id, "to_version": V2})
    applied = _call(
        upd_stand,
        headers,
        "apply_template_update",
        {"project_id": project_id, "to_version": V2, "fingerprint": plan["fingerprint"]},
    )

    assert status["recommended"]["version"] == V2
    for result in (planned, applied):
        assert result["isError"] is True
        assert result["_meta"]["code"] == "forbidden"
    after = _ok(_call(upd_stand, owner_headers, "template_update_status", {"project_id": project_id}))
    assert after["current_version"] == V1
    assert _audit(upd_stand, project_id) == []
