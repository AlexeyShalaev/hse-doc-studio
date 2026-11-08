"""list_project_fields и удаление ключей set_project_meta в локальной Студии (клиент SDK против приложения)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
import pytest_asyncio
from fastapi import FastAPI
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.factories import project_api_payload
from tests.fixtures.app import create_test_app, create_test_container

_BASE = "http://127.0.0.1"


@dataclass
class Studio:
    app: FastAPI
    rest: AsyncClient
    project_id: str
    folder: Path


@pytest_asyncio.fixture
async def studio(tmp_path: Path) -> AsyncIterator[Studio]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    folder = tmp_path / "kp"
    payload = {
        **project_api_payload(str(folder)),
        "name": "Курсовая",
        "pack_id": "hse-cs-sse",
        "template_id": "coursework",
        "version": "2026.1.2",
        "kind": "project",
        "meta": {"year": "2027"},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
        created = await rest.post("/api/v1/projects", json=payload)
        assert created.status_code == 201, created.text
        yield Studio(app=app, rest=rest, project_id=created.json()["id"], folder=folder)
    await container.close()


async def _enable(studio: Studio, **extra: object) -> None:
    resp = await studio.rest.put("/api/v1/mcp/settings", json={"enabled": True, **extra})
    assert resp.status_code == 200, resp.text


def _client(studio: Studio) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


def _fields(result: Any) -> dict[str, dict[str, Any]]:
    assert result.is_error is False, result.content
    return {f["key"]: f for f in json.loads(result.content[0].text)["fields"]}


async def test__list_project_fields__shows_template_fields_with_values_like_the_settings(studio: Studio) -> None:
    await _enable(studio)
    # Значение из настроек в вебе (PATCH проекта) видно в описании полей.
    patched = await studio.rest.patch(f"/api/v1/projects/{studio.project_id}", json={"meta": {"udc": "004.4"}})
    assert patched.status_code == 200, patched.text

    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        fields = _fields(await client.call_tool("list_project_fields", {"project_id": studio.project_id}))

    assert tools["list_project_fields"].input_schema["required"] == ["project_id"]
    assert "unset" in tools["set_project_meta"].input_schema["properties"]
    assert fields["udc"]["value"] == "004.4"
    assert fields["udc"]["required_at"] == "finalize"
    assert [d["id"] for d in fields["udc"]["printed_in"]] == ["report"]
    assert fields["year"]["value"] == "2027"
    assert fields["proposal_stage"]["options"] == ["Предварительная", "Доработанная"]
    assert fields["supervisor"]["missing"] is True


async def test__set_project_meta__unset__removes_the_key(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        added = await client.call_tool("set_project_meta", {"project_id": studio.project_id, "entries": {"udc": "004"}})
        removed = await client.call_tool("set_project_meta", {"project_id": studio.project_id, "unset": ["udc"]})
        fields = _fields(await client.call_tool("list_project_fields", {"project_id": studio.project_id}))

    assert added.is_error is False, added.content
    assert removed.is_error is False, removed.content
    meta = (await studio.rest.get(f"/api/v1/projects/{studio.project_id}")).json()["meta"]
    assert "udc" not in meta
    assert meta["year"] == "2027"
    assert fields["udc"]["value"] is None


async def test__list_project_fields__disabled_tool__refused(studio: Studio) -> None:
    await _enable(studio, disabled_tools=["list_project_fields"])

    async with _client(studio) as client:
        result = await client.call_tool("list_project_fields", {"project_id": studio.project_id})

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["code"] == "tool_disabled"


async def test__read_only_project__fields_readable_but_unset_refused(studio: Studio) -> None:
    await _enable(studio)
    state = studio.folder / ".hse-studio" / "project.json"
    data = json.loads(state.read_text(encoding="utf-8"))
    data["schema"] = {"version": 9, "read_compat": 1, "write_compat": 9, "written_by": "9.0.0"}
    state.write_text(json.dumps(data), encoding="utf-8")

    async with _client(studio) as client:
        listed = await client.call_tool("list_project_fields", {"project_id": studio.project_id})
        unset = await client.call_tool("set_project_meta", {"project_id": studio.project_id, "unset": ["year"]})

    assert listed.is_error is False, listed.content
    assert unset.is_error is True
    assert unset.meta is not None
    assert unset.meta["code"] == "read_only"
    assert json.loads(state.read_text(encoding="utf-8"))["meta"]["year"] == "2027"
