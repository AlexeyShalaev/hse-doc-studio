"""MCP локальной Студии: обновление шаблона тем же путём, что окно «Обновить шаблон» (статус, план, применение)."""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
import pytest
import pytest_asyncio
from fastapi import FastAPI
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.template_pack import (
    SUPERVISOR_V1,
    SUPERVISOR_V2,
    V1,
    V2,
    build_presets_pack,
    build_update_pack,
    project_payload,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")

_BASE = "http://127.0.0.1"
_TOOLS = ("template_update_status", "plan_template_update", "apply_template_update")


@dataclass
class Studio:
    app: FastAPI
    rest: AsyncClient
    project_id: str
    folder: Path


@asynccontextmanager
async def _studio(tmp_path: Path, build_pack: Callable[[Path], Path]) -> AsyncIterator[Studio]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    packs_dir = tmp_path / "packs"
    build_pack(packs_dir)
    container = create_test_container(data_dir, packs_dir=packs_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    folder = tmp_path / "kp"
    folder.mkdir()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
        created = await rest.post("/api/v1/projects", json=project_payload(folder))
        assert created.status_code == 201, created.text
        resp = await rest.put("/api/v1/mcp/settings", json={"enabled": True})
        assert resp.status_code == 200, resp.text
        yield Studio(app=app, rest=rest, project_id=created.json()["id"], folder=folder)
    await container.close()


@pytest_asyncio.fixture
async def studio(tmp_path: Path) -> AsyncIterator[Studio]:
    async with _studio(tmp_path, build_update_pack) as studio:
        yield studio


@pytest_asyncio.fixture
async def presets_studio(tmp_path: Path) -> AsyncIterator[Studio]:
    """Пак, где patch меняет только места подписей из шаблона (signing-route.md, 15.10)."""
    async with _studio(tmp_path, build_presets_pack) as studio:
        yield studio


def _client(studio: Studio) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


def _json(result: Any) -> Any:
    assert result.is_error is False, result.content
    return json.loads(result.content[0].text)


async def test__list_tools__local__offers_template_update_tools(studio: Studio) -> None:
    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert set(_TOOLS) <= set(tools)
    assert tools["template_update_status"].annotations is not None
    assert tools["template_update_status"].annotations.read_only_hint is True
    assert tools["apply_template_update"].input_schema["required"] == ["project_id", "to_version", "fingerprint"]


async def test__template_update__status_plan_apply__like_the_dialog(studio: Studio) -> None:
    async with _client(studio) as client:
        status = _json(await client.call_tool("template_update_status", {"project_id": studio.project_id}))
        plan = _json(
            await client.call_tool("plan_template_update", {"project_id": studio.project_id, "to_version": V2})
        )
        applied = _json(
            await client.call_tool(
                "apply_template_update",
                {"project_id": studio.project_id, "to_version": V2, "fingerprint": plan["fingerprint"]},
            )
        )
        after = _json(await client.call_tool("template_update_status", {"project_id": studio.project_id}))

    assert status["current_version"] == V1
    assert status["recommended"]["version"] == V2
    assert status["recommended"]["update_class"] == "patch"
    assert status["recommended"]["changes"] == ["Чёрный акцент и раздел «Заключение»"]
    assert {f["path"]: f["action"] for f in plan["files"]}["report/appendix.tex"] == "add"
    assert (plan["from_version"], plan["to_version"]) == (V1, V2)
    assert "report/appendix.tex" in applied["written"]
    assert applied["deleted"] == ["report/old.tex"]
    assert (studio.folder / "report" / "appendix.tex").exists()
    assert after["current_version"] == V2
    assert after["last_update"]["to_version"] == V2
    lock = json.loads((studio.folder / ".hse-studio" / "project.json").read_text(encoding="utf-8"))["lock"]
    assert lock["version"] == V2


async def test__apply__outdated_fingerprint__refused_and_nothing_written(studio: Studio) -> None:
    async with _client(studio) as client:
        result = await client.call_tool(
            "apply_template_update", {"project_id": studio.project_id, "to_version": V2, "fingerprint": "stale"}
        )
        status = _json(await client.call_tool("template_update_status", {"project_id": studio.project_id}))

    assert result.is_error is True
    assert status["current_version"] == V1
    assert not (studio.folder / "report" / "appendix.tex").exists()


async def test__plan__read_only_project__refused_like_http_423(studio: Studio) -> None:
    project_json = studio.folder / ".hse-studio" / "project.json"
    data = json.loads(project_json.read_text(encoding="utf-8"))
    data["schema"] = {"version": 7, "read_compat": 1, "write_compat": 7, "written_by": "9.0.0"}
    project_json.write_text(json.dumps(data), encoding="utf-8", newline="\n")

    async with _client(studio) as client:
        plan = await client.call_tool("plan_template_update", {"project_id": studio.project_id, "to_version": V2})
        apply = await client.call_tool(
            "apply_template_update", {"project_id": studio.project_id, "to_version": V2, "fingerprint": "x"}
        )

    for result in (plan, apply):
        assert result.is_error is True
        assert result.meta is not None
        assert result.meta["code"] == "read_only"
    assert not (studio.folder / "report" / "appendix.tex").exists()


async def test__plan_and_apply__signature_places_only(presets_studio: Studio) -> None:
    seed = SignaturePlacement(enabled=False, **SUPERVISOR_V1)
    JsonSignatureRepository().save_state(
        presets_studio.folder, SignaturesState(slots={}, placements={"report": {"supervisor": seed}})
    )
    project_id = presets_studio.project_id

    async with _client(presets_studio) as client:
        plan = _json(await client.call_tool("plan_template_update", {"project_id": project_id, "to_version": V2}))
        applied = _json(
            await client.call_tool(
                "apply_template_update",
                {"project_id": project_id, "to_version": V2, "fingerprint": plan["fingerprint"]},
            )
        )

    assert plan["files"] == []
    assert plan["signature_presets"] == {"updated": [{"doc_id": "report", "slot_id": "supervisor"}], "kept": []}
    assert applied["signature_places"] == [{"doc_id": "report", "slot_id": "supervisor"}]
    data = json.loads((presets_studio.folder / ".hse-studio" / "signatures.json").read_text(encoding="utf-8"))
    supervisor = data["placements"]["report"]["supervisor"]
    assert {k: supervisor[k] for k in SUPERVISOR_V2} == SUPERVISOR_V2
