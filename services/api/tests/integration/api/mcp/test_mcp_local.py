"""MCP локальной Студии: клиент SDK против настоящего приложения (docs/design/mcp.md, раздел 7)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import httpx2
import pytest
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
    folder = tmp_path / "vkr"
    folder.mkdir()
    async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
        created = await rest.post("/api/v1/projects", json=project_api_payload(str(folder)))
        assert created.status_code == 201, created.text
        yield Studio(app=app, rest=rest, project_id=created.json()["id"], folder=folder)
    await container.close()


async def _enable(studio: Studio, **extra: object) -> None:
    resp = await studio.rest.put("/api/v1/mcp/settings", json={"enabled": True, **extra})
    assert resp.status_code == 200, resp.text


def _client(studio: Studio, *, host: str = _BASE, mode: str = "legacy") -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=host)
    return Client(streamable_http_client(f"{host}/mcp", http_client=http), mode=mode)


async def test__mcp__disabled_by_default__answers_503(studio: Studio) -> None:
    resp = await studio.rest.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})

    assert resp.status_code == 503
    assert resp.json()["code"] == "mcp_disabled"


async def test__mcp__foreign_host__is_rejected(studio: Studio) -> None:
    await _enable(studio)

    resp = await studio.rest.post(
        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers={"Host": "evil.example"}
    )

    assert resp.status_code == 403


async def test__list_tools__enabled__hides_dangerous_and_server_only(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        names = {t.name for t in (await client.list_tools()).tools}

    assert {"list_projects", "read_tex", "write_file", "compile_document"} <= names
    assert "delete_file" not in names
    assert "list_review_threads" not in names
    assert not any(n.startswith("admin_") for n in names)


async def test__list_tools__project_tool__requires_project_id(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert tools["read_tex"].input_schema["required"][0] == "project_id"
    assert tools["read_tex"].annotations is not None
    assert tools["read_tex"].annotations.read_only_hint is True


async def test__call_tool__write_then_read__round_trips_through_the_project(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        written = await client.call_tool(
            "write_file", {"project_id": studio.project_id, "path": "notes.tex", "content": "Привет"}
        )
        read = await client.call_tool("read_tex", {"project_id": studio.project_id, "path": "notes.tex"})

    assert written.is_error is False, written.content
    assert (studio.folder / "notes.tex").read_text(encoding="utf-8") == "Привет"
    assert "1: Привет" in read.content[0].text


async def test__call_tool__list_projects__sees_the_project(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio, mode="auto") as client:
        result = await client.call_tool("list_projects", {})

    assert result.is_error is False
    assert "Test VKR" in result.content[0].text


async def test__call_tool__disabled_tool__answers_tool_disabled(studio: Studio) -> None:
    await _enable(studio, disabled_tools=["list_files"])

    async with _client(studio) as client:
        result = await client.call_tool("list_files", {"project_id": studio.project_id})

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["code"] == "tool_disabled"


async def test__call_tool__dangerous_enabled_by_name__deletes_the_file(studio: Studio) -> None:
    (studio.folder / "junk.tex").write_text("x", encoding="utf-8")
    await _enable(studio, enabled_dangerous=["delete_file"])

    async with _client(studio) as client:
        result = await client.call_tool("delete_file", {"project_id": studio.project_id, "path": "junk.tex"})

    assert result.is_error is False, result.content
    assert not (studio.folder / "junk.tex").exists()


async def test__call_tool__unknown_project__answers_not_found(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        result = await client.call_tool("list_files", {"project_id": "00000000-0000-0000-0000-000000000001"})

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["code"] == "not_found"


async def test__call_tool__bad_project_id__answers_invalid_arguments(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        result = await client.call_tool("list_files", {"project_id": "nope"})

    assert result.meta is not None
    assert result.meta["code"] == "invalid_arguments"


async def test__journal__records_calls_without_arguments(studio: Studio) -> None:
    await _enable(studio)
    async with _client(studio) as client:
        await client.call_tool("list_files", {"project_id": studio.project_id})

    calls = (await studio.rest.get("/api/v1/mcp/calls")).json()

    assert calls[0]["tool"] == "list_files"
    assert calls[0]["outcome"] == "ok"
    assert calls[0]["arg_keys"] == ["project_id"]


async def test__read_resource__project_file__returns_text(studio: Studio) -> None:
    (studio.folder / "a.tex").write_text("abc", encoding="utf-8")
    await _enable(studio)

    async with _client(studio) as client:
        result = await client.read_resource(f"studio://projects/{studio.project_id}/files/a.tex")

    assert result.contents[0].text == "abc"  # type: ignore[union-attr]


async def test__prompts__fix_build__renders_with_arguments(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        prompts = {p.name for p in (await client.list_prompts()).prompts}
        prompt = await client.get_prompt("fix_build", {"project_id": studio.project_id, "doc_id": "vkr"})

    assert {"fix_build", "normcontrol", "review_changes"} <= prompts
    assert studio.project_id in prompt.messages[0].content.text  # type: ignore[union-attr]


async def test__settings__unknown_tool__is_rejected(studio: Studio) -> None:
    resp = await studio.rest.put("/api/v1/mcp/settings", json={"disabled_tools": ["no_such_tool"]})

    assert resp.status_code == 400


async def test__info__reports_enabled_tools(studio: Studio) -> None:
    await _enable(studio)

    info = (await studio.rest.get("/api/v1/mcp/info")).json()

    assert info["enabled"] is True
    assert info["mode"] == "local"
    assert info["token_scope"] is None
    assert "list_projects" in info["tools"]


@pytest.mark.parametrize("payload", [{"enabled": True}])
async def test__settings__saved__persist_in_config(studio: Studio, payload: dict[str, object]) -> None:
    await studio.rest.put("/api/v1/mcp/settings", json=payload)

    stored = json.loads((await studio.rest.get("/api/v1/mcp/settings")).text)

    assert stored["enabled"] is True
    assert stored["disabled_groups"] == ["admin"]
