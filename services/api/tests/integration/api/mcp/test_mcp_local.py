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
from hse_doc_studio.infra.di.providers.local_git_servers import LocalGitServersProvider
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


async def test__list_tools__local__create_project_requires_folder_and_clone_is_offered(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert "folder" in tools["create_project"].input_schema["required"]
    assert "ask_user" not in (tools["create_project"].description or "")
    assert "clone_cloud_project" in tools
    assert "set_project_people" in tools


async def test__call_tool__set_project_people__updates_the_project_like_the_web(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        result = await client.call_tool(
            "set_project_people",
            {
                "project_id": studio.project_id,
                "supervisor": {"name": "Петров П. П.", "title": "доцент", "degree": "канд. техн. наук"},
                "co_supervisor": {"name": "Сидоров С. С.", "role": "company"},
                "authors": [{"name": "Иванов Иван Иванович", "group": "БПИ221"}, {"name": "Анна Смирнова"}],
            },
        )
        cleared = await client.call_tool(
            "set_project_people", {"project_id": studio.project_id, "clear": ["co_supervisor"]}
        )

    assert result.is_error is False, result.content
    assert cleared.is_error is False, cleared.content
    project = (await studio.rest.get(f"/api/v1/projects/{studio.project_id}")).json()
    assert project["supervisor"] == {
        "name": "Петров П. П.",
        "role": "university",
        "title": "доцент",
        "degree": "канд. техн. наук",
    }
    assert project["co_supervisor"] is None
    assert [(a["name"], a["group"]) for a in project["authors"]] == [
        ("Иванов Иван Иванович", "БПИ221"),
        ("Анна Смирнова", None),
    ]
    calls = (await studio.rest.get("/api/v1/mcp/calls", params={"tool": "set_project_people"})).json()
    assert [c["outcome"] for c in calls] == ["ok", "ok"]


async def test__call_tool__set_project_people__no_changes__invalid_arguments(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        result = await client.call_tool("set_project_people", {"project_id": studio.project_id})

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["code"] == "invalid_arguments"


def _presentation(studio: Studio) -> dict[str, object]:
    data = json.loads((studio.folder / ".hse-studio" / "project.json").read_text(encoding="utf-8"))
    return next(d for d in data["documents"] if d["id"] == "presentation")


async def test__call_tool__set_document_variant__switches_like_the_settings(studio: Studio) -> None:
    await _enable(studio)

    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        shown = await client.call_tool(
            "set_document_variant", {"project_id": studio.project_id, "doc_id": "presentation"}
        )
        switched = await client.call_tool(
            "set_document_variant", {"project_id": studio.project_id, "doc_id": "presentation", "variant": "beamer"}
        )

    assert tools["set_document_variant"].input_schema["required"] == ["project_id", "doc_id"]
    assert shown.is_error is False, shown.content
    assert {v["id"] for v in json.loads(shown.content[0].text)["variants"]} >= {"pptx", "beamer"}  # type: ignore[union-attr]
    assert switched.is_error is False, switched.content
    assert json.loads(switched.content[0].text)["changed"] is True  # type: ignore[union-attr]
    document = (await studio.rest.get(f"/api/v1/projects/{studio.project_id}/documents/presentation")).json()
    assert document["chosen_variant"] == "beamer"


async def test__call_tool__set_document_variant__unknown_variant__lists_allowed(studio: Studio) -> None:
    await _enable(studio)
    before = _presentation(studio)["chosen_variant"]

    async with _client(studio) as client:
        result = await client.call_tool(
            "set_document_variant", {"project_id": studio.project_id, "doc_id": "presentation", "variant": "keynote"}
        )

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["code"] == "invalid_arguments"
    assert "beamer" in result.content[0].text  # type: ignore[union-attr]
    assert _presentation(studio)["chosen_variant"] == before


async def test__call_tool__set_document_variant__read_only_project__refused(studio: Studio) -> None:
    """Проект записан более новой Студией: PATCH документа в вебе отвечает 423, тул отказывает так же."""
    await _enable(studio)
    project_file = studio.folder / ".hse-studio" / "project.json"
    data = json.loads(project_file.read_text(encoding="utf-8"))
    data["schema"] = {"version": 7, "read_compat": 1, "write_compat": 7, "written_by": "9.0.0"}
    project_file.write_text(json.dumps(data), encoding="utf-8")
    before = _presentation(studio)["chosen_variant"]

    async with _client(studio) as client:
        result = await client.call_tool(
            "set_document_variant", {"project_id": studio.project_id, "doc_id": "presentation", "variant": "beamer"}
        )

    assert result.is_error is True
    assert result.meta is not None
    assert result.meta["code"] == "read_only"
    assert _presentation(studio)["chosen_variant"] == before


@pytest_asyncio.fixture
async def studio_with_cloud(tmp_path: Path) -> AsyncIterator[FastAPI]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir, extra_providers=[LocalGitServersProvider()])
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
        resp = await rest.put("/api/v1/mcp/settings", json={"enabled": True})
        assert resp.status_code == 200, resp.text
    yield app
    await container.close()


async def test__call_tool__clone_cloud_project__server_not_connected__explains(studio_with_cloud: FastAPI) -> None:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio_with_cloud), base_url=_BASE)
    url = "https://studio.example.org/projects/11111111-1111-4111-8111-111111111111/"

    async with Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy") as client:
        result = await client.call_tool("clone_cloud_project", {"url": url, "wait_s": 0})

    assert result.is_error is True
    assert result.content[0].text.startswith(("Сервер studio.example.org не подключён", "The server studio"))  # type: ignore[union-attr]


async def test__call_tool__get_project__foreign_last_compile__is_replaced_by_a_local_one(studio: Studio) -> None:
    """project.json пришёл из облака (git-синхронизация): ссылка облачной сборки здесь не находится get_compile."""
    await _enable(studio)
    project_file = studio.folder / ".hse-studio" / "project.json"
    data = json.loads(project_file.read_text(encoding="utf-8"))
    doc_id = data["documents"][0]["id"]
    data["documents"][0]["last_compile_id"] = "039ea6b1-7bee-48b4-9613-589f292f779e"
    project_file.write_text(json.dumps(data), encoding="utf-8")

    async with _client(studio) as client:
        result = await client.call_tool("get_project", {"project_id": studio.project_id})

    assert result.is_error is False, result.content
    documents = {d["id"]: d for d in json.loads(result.content[0].text)["documents"]}
    assert documents[doc_id]["last_compile_id"] is None
