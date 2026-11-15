"""MCP Студии шаблонов (template-studio.md, раздел 11, срез T16): клиент SDK против локальной Студии.

Тулы `pack_*` видны, только когда раздел включён; пространство над папкой с маленьким паком (выпущенная 2026.1.0 и
черновик 2026.1.1): дерево и модель версии, чтение и запись файлов с защитой выпущенной, проверка, класс, новая
версия и заметки, места подписей, сводка перед «Предложить изменения».
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx2
import pytest_asyncio
import yaml
from fastapi import FastAPI
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.fixtures.app import create_test_app, create_test_container
from tests.integration.api.pack_studio.conftest import DRAFT, DRAFT_DIR, RELEASED_DIR, write_pack
from tests.integration.api.pack_studio.test_git_workspace import _remote

_BASE = "http://127.0.0.1"
_DRAFT = f"demo/report/{DRAFT}"


@dataclass
class Studio:
    app: FastAPI
    rest: AsyncClient
    folder: Path
    root: Path


@pytest_asyncio.fixture
async def studio(tmp_path: Path) -> AsyncIterator[Studio]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    saved = app_settings.pack_studio.model_copy()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    folder = write_pack(tmp_path / "packs")
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
            resp = await rest.put("/api/v1/mcp/settings", json={"enabled": True})
            assert resp.status_code == 200, resp.text
            yield Studio(app=app, rest=rest, folder=folder, root=tmp_path)
    finally:
        await container.close()
        app_settings.pack_studio = saved


async def _open(studio: Studio) -> str:
    resp = await studio.rest.put("/api/v1/pack-studio/section", json={"enabled": True})
    assert resp.status_code == 200, resp.text
    resp = await studio.rest.post(
        "/api/v1/pack-studio/workspaces", json={"kind": "folder", "folder": str(studio.folder)}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def _client(studio: Studio) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


async def _call(client: Client, name: str, args: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    result = await client.call_tool(name, args)
    text = result.content[0].text  # type: ignore[union-attr]
    assert result.is_error is (not ok), text
    return dict(json.loads(text))


async def test__list_tools__pack_tools_only_with_the_section_open(studio: Studio) -> None:
    async with _client(studio) as client:
        closed = {t.name for t in (await client.list_tools()).tools}
    await _open(studio)
    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert not [n for n in closed if n.startswith("pack_")]
    assert {"pack_list_workspaces", "pack_read", "pack_write_file", "pack_lint", "pack_new_version"} <= set(tools)
    # «Предложить изменения» пушит и открывает PR: опасный, включается поимённо.
    assert "pack_propose" not in tools
    assert "project_id" not in tools["pack_read"].input_schema["properties"]
    assert tools["pack_read"].annotations is not None
    assert tools["pack_read"].annotations.read_only_hint is True


async def test__call__section_closed__pack_studio_refusal(studio: Studio) -> None:
    async with _client(studio) as client:
        body = await _call(client, "pack_list_workspaces", {}, ok=False)

    assert body["code"] == "pack_studio_disabled"


async def test__read__tree_model_and_files(studio: Studio) -> None:
    ws_id = await _open(studio)

    async with _client(studio) as client:
        listed = await _call(client, "pack_list_workspaces", {})
        tree = await _call(client, "pack_read", {"workspace_id": ws_id})
        model = await _call(client, "pack_read", {"workspace_id": ws_id, "version": _DRAFT})
        released = await _call(
            client, "pack_read_file", {"workspace_id": ws_id, "path": f"{RELEASED_DIR}/version.yaml"}
        )

    assert listed["workspaces"][0]["id"] == ws_id
    assert listed["workspaces"][0]["kind"] == "folder"
    versions = {v["version"]: v["released"] for v in tree["packs"][0]["templates"][0]["versions"]}
    assert versions == {"2026.1.0": True, DRAFT: False}
    assert model["version"] == DRAFT
    assert model["released"] is False
    assert model["langs"] == ["ru"]
    assert f"{DRAFT_DIR}/files/report/main.tex" in [f["path"] for f in model["files"]]
    assert released["read_only"] == "version_released"
    assert released["content"].startswith("# Демо-версия")


async def test__write__draft_saved_released_refused_stale_detected(studio: Studio) -> None:
    ws_id = await _open(studio)
    path = f"{DRAFT_DIR}/files/report/main.tex"

    async with _client(studio) as client:
        before = await _call(client, "pack_read_file", {"workspace_id": ws_id, "path": path})
        written = await _call(
            client,
            "pack_write_file",
            {"workspace_id": ws_id, "path": path, "content": "% новый текст\n", "if_match": before["etag"]},
        )
        stale = await _call(
            client,
            "pack_write_file",
            {"workspace_id": ws_id, "path": path, "content": "x", "if_match": before["etag"]},
            ok=False,
        )
        refused = await _call(
            client,
            "pack_write_file",
            {"workspace_id": ws_id, "path": f"{RELEASED_DIR}/files/report/main.tex", "content": "x"},
            ok=False,
        )

    assert written["etag"] != before["etag"]
    assert (studio.folder / path).read_text(encoding="utf-8") == "% новый текст\n"
    assert (stale["code"], stale["etag"]) == ("stale_file", written["etag"])
    assert refused["code"] == "version_released"


async def test__lint_classify_new_version_and_notes(studio: Studio) -> None:
    ws_id = await _open(studio)

    async with _client(studio) as client:
        lint = await _call(client, "pack_lint", {"workspace_id": ws_id, "path": f"{DRAFT_DIR}/version.yaml"})
        state = await _call(client, "pack_classify", {"workspace_id": ws_id, "version": _DRAFT})
        created = await _call(
            client,
            "pack_new_version",
            {"workspace_id": ws_id, "pack": "demo", "template": "report", "update_class": "minor"},
        )
        noted = await _call(
            client,
            "pack_version_notes",
            {
                "workspace_id": ws_id,
                "version": created["version"],
                "changes": {"ru": ["Новый раздел"], "en": ["A new section"]},
            },
        )
        bad = await client.call_tool("pack_classify", {"workspace_id": ws_id, "version": "demo/report"})

    assert lint["scope"] == "version"
    assert lint["target"] == DRAFT_DIR
    assert state["base"] == "2026.1.0"
    assert state["released"] is False
    assert created["version"] == "demo/templates/report/versions/2026.2.0"
    manifest = yaml.safe_load((studio.folder / created["version"] / "version.yaml").read_text(encoding="utf-8"))
    assert manifest["status"] == "beta"
    assert noted["changes"] == {"ru": ["Новый раздел"], "en": ["A new section"]}
    assert bad.is_error is True
    assert bad.meta is not None
    assert bad.meta["code"] == "invalid_arguments"


async def test__placement_and_propose_on_a_folder(studio: Studio) -> None:
    ws_id = await _open(studio)
    resp = await studio.rest.put("/api/v1/mcp/settings", json={"enabled": True, "enabled_dangerous": ["pack_propose"]})
    assert resp.status_code == 200, resp.text

    async with _client(studio) as client:
        places = await _call(client, "pack_set_placement", {"workspace_id": ws_id, "version": _DRAFT})
        no_slot = await _call(
            client,
            "pack_set_placement",
            {
                "workspace_id": ws_id,
                "version": _DRAFT,
                "ops": [
                    {"op": "set_place", "slot": "author", "box": {"page": 1, "x_mm": 10, "y_mm": 10, "width_mm": 30}}
                ],
            },
            ok=False,
        )
        propose = await _call(client, "pack_propose", {"workspace_id": ws_id}, ok=False)

    assert places["path"] == f"{DRAFT_DIR}/version.yaml"
    assert places["places"]["slots"] == []
    assert no_slot["code"] == "place_invalid"
    assert propose["code"] == "not_a_git_workspace"


async def test__propose__without_confirm__only_a_summary_of_the_git_workspace(studio: Studio) -> None:
    await _open(studio)
    await studio.rest.put("/api/v1/mcp/settings", json={"enabled": True, "enabled_dangerous": ["pack_propose"]})
    remote = _remote(studio.root / "remote")
    resp = await studio.rest.post("/api/v1/pack-studio/workspaces", json={"kind": "git", "url": remote.url})
    assert resp.status_code == 202, resp.text
    ws_id = str(resp.json()["id"])
    for _ in range(600):
        card = (await studio.rest.get(f"/api/v1/pack-studio/workspaces/{ws_id}")).json()
        if not card["busy"]:
            break
        await asyncio.sleep(0.05)
    assert card["state"] == "ready", card
    path = f"{DRAFT_DIR}/files/report/main.tex"

    async with _client(studio) as client:
        await _call(client, "pack_write_file", {"workspace_id": ws_id, "path": path, "content": "% правка\n"})
        summary = await _call(client, "pack_propose", {"workspace_id": ws_id})
        status = await _call(client, "pack_git_status", {"workspace_id": ws_id})

    assert summary["confirm_required"] is True
    assert summary["nothing_to_propose"] is False
    assert summary["repository"] == remote.url
    assert [c["path"] for c in summary["uncommitted"]] == [path]
    assert status["branch"] is None
    # Сводка ничего не отправляет: на сервере нет рабочей ветки.
    assert "pack-studio" not in remote.git("branch", "--list")


async def test__scaffold__options_new_pack_and_template_copy(studio: Studio) -> None:
    ws_id = await _open(studio)

    async with _client(studio) as client:
        options = await _call(client, "pack_scaffold_options", {"workspace_id": ws_id})
        created = await _call(
            client,
            "pack_create",
            {
                "workspace_id": ws_id,
                "pack_id": "my-pack",
                "name": {"ru": "Мой пак", "en": "My pack"},
                "maintainer_name": "Автор Паков",
                "template_id": "report",
                "template_name": {"ru": "Отчёт", "en": "Report"},
                "version": "2026.1",
            },
        )
        lint = await _call(client, "pack_lint", {"workspace_id": ws_id, "path": created["manifests"][-1]})
        copied = await _call(
            client,
            "pack_new_template",
            {
                "workspace_id": ws_id,
                "pack": "demo",
                "template_id": "practice",
                "template_name": "Практика",
                "copy_from": {"origin": "workspace", "pack": "demo", "template": "report", "version": "2026.1.0"},
            },
        )
        taken = await _call(
            client,
            "pack_create",
            {
                "workspace_id": ws_id,
                "pack_id": "hse-cs-sse",
                "name": {"ru": "Дубль"},
                "template_id": "x",
                "template_name": {"ru": "Икс"},
            },
            ok=False,
        )

    assert {"demo", "hse-cs-sse"} <= set(options["taken_packs"])
    assert ("catalog", "hse-cs-sse") in {(p["origin"], p["pack"]) for p in options["sources"]}
    assert created["version"] == "my-pack/templates/report/versions/2026.1"
    assert created["pack_created"] is True
    assert created["main_file"].endswith("files/report/report.tex")
    pack = yaml.safe_load((studio.folder / "my-pack" / "pack.yaml").read_text(encoding="utf-8"))
    assert pack["maintainer"] == {"name": "Автор Паков"}
    assert lint["errors"] == 0
    assert copied["pack_created"] is False
    assert copied["source"] == {"origin": "workspace", "pack": "demo", "template": "report", "version": "2026.1.0"}
    assert (studio.folder / "demo" / "templates" / "practice" / "template.yaml").is_file()
    assert (taken["code"], taken["where"]) == ("pack_id_taken", "studio")
