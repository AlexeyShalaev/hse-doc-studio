"""MCP: всё, что делает Студия шаблонов в интерфейсе, делается и тулами (pack-studio parity).

Клиент SDK против локальной Студии, настоящий DI и настоящие службы. Репозиторий паков голый, по file:// (провайдер
`other`: push без PR), сети нет. Версии настоящие (ВКР `hse-cs-se` 2026.1.2 и черновик 2026.1.9, который можно
править). Полный цикл агента: пространство, ветка, правка, проверка, результат, сценарий, коммит, предложение.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx2
import pytest
import pytest_asyncio
import yaml
from fastapi import FastAPI
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.git_remote import BareRemote
from tests.integration.api.pack_studio.conftest import Stand
from tests.integration.api.pack_studio.outcome_support import DRAFT, DRAFT_MANIFEST, DRAFT_VKR
from tests.integration.api.pack_studio.test_outcome_git import _PROFILE, _packs_remote

_BASE = "http://127.0.0.1"
TODAY = date(2026, 11, 16)
_DRAFT = "/".join(DRAFT_VKR)
_TEMPLATE = "hse-cs-se/vkr"
_DRAFT_DIR = f"hse-cs-se/templates/vkr/versions/{DRAFT}"


@dataclass
class Studio:
    app: FastAPI
    stand: Stand

    @property
    def rest(self) -> AsyncClient:
        return self.stand.client


@pytest_asyncio.fixture
async def studio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Studio]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    saved = app_settings.pack_studio.model_copy()
    container = create_test_container(data_dir)
    app = create_test_app(container)
    install_mcp(app, mode=StudioMode.local)
    monkeypatch.setattr(await container.get(PackOutcomeService), "_today", lambda: TODAY)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
            resp = await rest.put("/api/v1/mcp/settings", json={"enabled": True, "enabled_dangerous": ["pack_propose"]})
            assert resp.status_code == 200, resp.text
            resp = await rest.put("/api/v1/profile", json=_PROFILE)
            assert resp.status_code == 200, resp.text
            stand = Stand(rest, tmp_path, container)
            await stand.enable()
            yield Studio(app=app, stand=stand)
    finally:
        await container.close()
        app_settings.pack_studio = saved


def _client(studio: Studio) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


async def _text(client: Client, name: str, args: dict[str, Any], *, ok: bool = True) -> str:
    result = await client.call_tool(name, args)
    text = str(result.content[0].text)  # type: ignore[union-attr]
    assert result.is_error is (not ok), text
    return text


async def _json(client: Client, name: str, args: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    return dict(json.loads(await _text(client, name, {**args, "format": "json"}, ok=ok)))


async def _refused(client: Client, name: str, args: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(await _text(client, name, args, ok=False)))


async def _connect(studio: Studio, client: Client) -> tuple[BareRemote, str]:
    remote = _packs_remote(studio.stand.root)
    created = await _json(client, "pack_workspace_create", {"url": remote.url})
    assert created["state"] == "cloning", created
    for _ in range(600):
        card = next(
            w for w in (await _json(client, "pack_list_workspaces", {}))["workspaces"] if w["id"] == created["id"]
        )
        if not card["busy"]:
            break
        await asyncio.sleep(0.05)
    assert card["state"] == "ready", card
    return remote, str(created["id"])


# ── видимость ────────────────────────────────────────────────────────────────


async def test__list_tools__new_tools_follow_the_section_and_annotate_read_and_write(studio: Studio) -> None:
    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    for name in ("pack_help", "pack_tree", "pack_git_diff", "pack_scenario_run", "pack_outcome_atlas"):
        assert tools[name].annotations is not None
        assert tools[name].annotations.read_only_hint is True, name
    for name in ("pack_patch_yaml", "pack_git_commit", "pack_workspace_delete", "pack_scenario_write"):
        assert tools[name].annotations is not None
        assert tools[name].annotations.read_only_hint is False, name
    assert {"pack_git_start_over", "pack_delete_file", "pack_workspace_create", "pack_catalog"} <= set(tools)
    assert tools["pack_patch_yaml"].input_schema["required"] == ["workspace_id", "path", "ops"]


async def test__closed_section__new_tools_hidden_and_refused(studio: Studio) -> None:
    resp = await studio.rest.put("/api/v1/pack-studio/section", json={"enabled": False})
    assert resp.status_code == 200, resp.text

    async with _client(studio) as client:
        names = {t.name for t in (await client.list_tools()).tools}
        body = await _refused(client, "pack_help", {})

    assert not [n for n in names if n.startswith("pack_")]
    assert body["code"] == "pack_studio_disabled"


# ── справка ──────────────────────────────────────────────────────────────────


async def test__help__lists_every_tool_and_the_typical_flow(studio: Studio) -> None:
    async with _client(studio) as client:
        listed = {t.name for t in (await client.list_tools()).tools if t.name.startswith("pack_")}
        data = await _json(client, "pack_help", {})
        flow = await _text(client, "pack_help", {"topic": "flow"})
        git_only = await _json(client, "pack_help", {"topic": "git"})
        text = await _text(client, "pack_help", {})

    in_help = {e["name"] for entries in data["groups"].values() for e in entries}
    assert listed - {"pack_help"} <= in_help, sorted(listed - {"pack_help"} - in_help)
    order = [
        flow.index(n)
        for n in ("pack_git_branch", "pack_patch_yaml", "pack_lint", "pack_outcome", "pack_git_commit", "pack_propose")
    ]
    assert order == sorted(order)
    assert list(git_only["groups"]) == ["git"]
    assert "pack_propose [exec, off by default]" in text or "pack_propose" in text


# ── пространства ─────────────────────────────────────────────────────────────


async def test__workspace__create_refresh_delete_with_confirm_and_no_secrets(studio: Studio) -> None:
    async with _client(studio) as client:
        remote, ws = await _connect(studio, client)
        secret = await _refused_call(client, {"url": remote.url, "token": "ghp_x"})
        missing = await _refused(
            client,
            "pack_workspace_create",
            {"url": remote.url, "credential_id": "00000000-0000-0000-0000-000000000001"},
        )
        credentials = await _json(client, "pack_list_credentials", {})
        refreshed = await _json(client, "pack_workspace_refresh", {"workspace_id": ws})
        preview = await _json(client, "pack_workspace_delete", {"workspace_id": ws})
        still = (await _json(client, "pack_list_workspaces", {}))["workspaces"]
        gone = await _json(client, "pack_workspace_delete", {"workspace_id": ws, "confirm": True})
        after = (await _json(client, "pack_list_workspaces", {}))["workspaces"]
        official = await _json(client, "pack_official", {})

    assert "интерфейсе" in secret
    assert "token" in secret
    assert missing["code"] == "credentials_missing"
    assert "pack_list_credentials" in missing["hint"]
    assert credentials == {"credentials": []}
    assert refreshed["id"] == ws
    assert preview["confirm_required"] is True
    assert preview["loses_local_copy"] is True
    assert [w["id"] for w in still] == [ws]
    assert gone["deleted"] is True
    assert after == []
    assert official["repo"] is None or "url" in official["repo"]


async def _refused_call(client: Client, args: dict[str, Any]) -> str:
    result = await client.call_tool("pack_workspace_create", args)
    assert result.is_error
    return str(result.content[0].text)  # type: ignore[union-attr]


async def test__workspace__folder_kind_and_catalog_local_flow(studio: Studio, tmp_path: Path) -> None:
    from tests.integration.api.pack_studio.outcome_support import copy_real_packs  # noqa: PLC0415

    root = copy_real_packs(tmp_path / "folderpacks" / "packs")
    async with _client(studio) as client:
        ws = await _json(
            client, "pack_workspace_create", {"kind": "folder", "folder": str(root.parent), "packs_path": "packs"}
        )
        status = await _json(client, "pack_catalog", {"workspace_id": ws["id"]})
        checked = await _json(client, "pack_catalog", {"workspace_id": ws["id"], "action": "check"})
        no_confirm = await _json(
            client, "pack_catalog", {"workspace_id": ws["id"], "action": "apply", "revision": checked["revision"]}
        )
        disabled = await _json(client, "pack_catalog", {"workspace_id": ws["id"], "action": "disable"})
        bad_action = await client.call_tool("pack_catalog", {"workspace_id": ws["id"], "action": "nope"})

    assert ws["kind"] == "folder"
    assert status["source"] is None
    assert checked["revision"]
    assert isinstance(checked["ok"], bool)
    assert no_confirm["confirm_required"] is True
    assert disabled["enabled"] is False
    assert bad_action.is_error is True


# ── чтение и правка ──────────────────────────────────────────────────────────


async def test__edit__tree_model_patch_preserves_comments_and_checks_etag_and_schema(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        tree = await _json(client, "pack_tree", {"workspace_id": ws, "prefix": _DRAFT_DIR + "/files", "max_files": 5})
        model = await _json(client, "pack_model", {"workspace_id": ws, "version": _DRAFT})
        before = await _json(client, "pack_read_file", {"workspace_id": ws, "path": DRAFT_MANIFEST})
        patched = await _json(
            client,
            "pack_patch_yaml",
            {
                "workspace_id": ws,
                "path": DRAFT_MANIFEST,
                "if_match": model["manifest"]["etag"],
                "ops": [
                    {"op": "set", "pointer": "/summary/en", "value": "Edited by an agent."},
                    {"op": "insert", "pointer": "/changes/en/-", "value": "Agent note"},
                    {"op": "insert", "pointer": "/changes/ru/-", "value": "Заметка агента"},
                ],
            },
        )
        stale = await _refused(
            client,
            "pack_patch_yaml",
            {
                "workspace_id": ws,
                "path": DRAFT_MANIFEST,
                "if_match": model["manifest"]["etag"],
                "ops": [{"op": "set", "pointer": "/summary/en", "value": "x"}],
            },
        )
        broken = await _refused(
            client,
            "pack_patch_yaml",
            {
                "workspace_id": ws,
                "path": DRAFT_MANIFEST,
                "if_match": patched["etag"],
                "ops": [{"op": "set", "pointer": "/summary/en/deeper/0", "value": "x"}],
            },
        )
        released = await _refused(
            client,
            "pack_patch_yaml",
            {
                "workspace_id": ws,
                "path": "hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml",
                "ops": [{"op": "set", "pointer": "/summary/en", "value": "x"}],
            },
        )
        after = await _json(client, "pack_read_file", {"workspace_id": ws, "path": DRAFT_MANIFEST})
        lint = await _json(client, "pack_lint", {"workspace_id": ws, "path": _DRAFT_DIR})

    assert tree["files_total"] > 0
    assert len(tree["files"]) <= 5
    assert model["manifest"]["etag"] == before["etag"]
    assert {d["id"] for d in model["documents"]}
    assert patched["ops"] == 3
    assert patched["etag"] == after["etag"] != before["etag"]
    # Комментарии и остальной текст остались: изменились только названные узлы.
    assert after["content"].startswith("# packs/hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml")
    data = yaml.safe_load(after["content"])
    assert data["summary"]["en"] == "Edited by an agent."
    assert data["changes"]["en"][-1] == "Agent note"
    assert stale["code"] == "stale_file"
    assert "pack_read_file" in stale["hint"]
    assert broken["code"] in {"yaml_patch_conflict", "model_invalid"}
    assert released["code"] == "version_released"
    assert "pack_new_version" in released["hint"]
    assert lint["errors"] == 0, lint["findings"]


async def test__edit__move_and_delete_file_with_confirm(studio: Studio) -> None:
    src = f"{_DRAFT_DIR}/files/extra.txt"
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        await _json(client, "pack_write_file", {"workspace_id": ws, "path": src, "content": "один\n"})
        moved = await _json(
            client, "pack_move_file", {"workspace_id": ws, "src": src, "dst": f"{_DRAFT_DIR}/files/moved.txt"}
        )
        taken = await _refused(
            client,
            "pack_move_file",
            {"workspace_id": ws, "src": f"{_DRAFT_DIR}/files/moved.txt", "dst": f"{_DRAFT_DIR}/version.yaml"},
        )
        preview = await _json(client, "pack_delete_file", {"workspace_id": ws, "path": moved["to"]})
        still = await _json(client, "pack_read_file", {"workspace_id": ws, "path": moved["to"]})
        deleted = await _json(client, "pack_delete_file", {"workspace_id": ws, "path": moved["to"], "confirm": True})
        gone = await _refused(client, "pack_read_file", {"workspace_id": ws, "path": moved["to"]})
        released = await _refused(
            client,
            "pack_delete_file",
            {"workspace_id": ws, "path": "hse-cs-se/templates/vkr/versions/2026.1.2/version.yaml", "confirm": True},
        )

    assert moved["moved"] is True
    assert taken["code"] == "file_exists"
    assert preview["confirm_required"] is True
    assert still["content"] == "один\n"
    assert deleted["deleted"] is True
    assert gone["code"] == "file_not_found"
    assert released["code"] == "version_released"


async def test__edit__model_action_hints_library_and_submission(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        hints = await _json(client, "pack_hints", {"workspace_id": ws, "path": f"{_DRAFT_DIR}/version.yaml"})
        library = await _json(client, "pack_doc_library", {"workspace_id": ws})
        model = await _json(client, "pack_model", {"workspace_id": ws, "version": _DRAFT})
        submission = await _json(client, "pack_submission", {"workspace_id": ws, "version": _DRAFT})
        routes = await _text(client, "pack_submission", {"workspace_id": ws, "version": _DRAFT, "routes": True})
        edited = await _json(
            client,
            "pack_submission_edit",
            {
                "workspace_id": ws,
                "version": _DRAFT,
                "if_match": submission["etag"],
                "ops": [
                    {
                        "op": "set_profile",
                        "profile": 0,
                        "head": {
                            "id": submission["submission"]["profiles"][0]["id"],
                            "name": {"ru": "Новое имя", "en": "New name"},
                            "description": {"ru": "Описание", "en": "Description"},
                        },
                    }
                ],
            },
        )
        bad = await _refused(
            client,
            "pack_submission_edit",
            {"workspace_id": ws, "version": _DRAFT, "ops": [{"op": "remove_profile", "profile": 99}]},
        )
        no_confirm = await _json(
            client,
            "pack_model_action",
            {
                "workspace_id": ws,
                "version": _DRAFT,
                "action": "remove_document",
                "document": model["documents"][0]["id"],
            },
        )
        released = await _refused(
            client,
            "pack_model_action",
            {
                "workspace_id": ws,
                "version": "hse-cs-se/vkr/2026.1.2",
                "action": "rename_field",
                "field": "x",
                "to": "y",
            },
        )

    assert hints["version"] == _DRAFT_DIR
    assert hints["meta_fields"]
    assert library["documents"]
    assert submission["submission"]["profiles"]
    assert "Маршруты" in routes
    assert edited["etag"] != submission["etag"]
    assert edited["submission"]["profiles"][0]["name"]["ru"] == "Новое имя"
    assert bad["code"] in {"submission_invalid", "version_released"}
    assert no_confirm["confirm_required"] is True
    assert released["code"] == "version_released"


# ── сценарии и обзоры результата ─────────────────────────────────────────────


async def test__scenarios__create_edit_run_snapshot_delete_restore_and_conflicts(studio: Studio) -> None:
    base = {"workspace_id": "", "template": _TEMPLATE}
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        base["workspace_id"] = ws
        created = await _json(
            client,
            "pack_scenario_write",
            {**base, "id": "agent-one", "name": "Сценарий агента", "inputs": {"kind": "research"}, "versions": [DRAFT]},
        )
        taken = await _refused(client, "pack_scenario_write", {**base, "id": "agent-one", "name": "Другой"})
        listed = await _json(client, "pack_scenario_list", base)
        etag = created["etag"]
        edited = await _json(
            client,
            "pack_scenario_write",
            {
                **base,
                "id": "agent-one",
                "if_match": etag,
                "inputs": {"kind": "project"},
                "record_snapshot": "work_tree",
                "version": DRAFT,
            },
        )
        stale = await _refused(
            client, "pack_scenario_write", {**base, "id": "agent-one", "if_match": etag, "inputs": {"kind": "research"}}
        )
        run = await _json(client, "pack_scenario_run", {**base, "version": DRAFT})
        run_text = await _text(client, "pack_scenario_run", {**base, "version": DRAFT})
        matrix = await _json(client, "pack_outcome_matrix", {"workspace_id": ws, "version": _DRAFT})
        matrix_text = await _text(client, "pack_outcome_matrix", {"workspace_id": ws, "version": _DRAFT})
        missing = await _refused(client, "pack_scenario_run", {**base, "scenarios": ["no-such"]})
        deleted = await _json(client, "pack_scenario_delete", {**base, "id": "agent-one"})
        restored = await _json(
            client,
            "pack_scenario_write",
            {
                **base,
                "id": "agent-one",
                "name": deleted["scenario"]["name"],
                "inputs": deleted["scenario"]["inputs"],
                "versions": deleted["scenario"]["versions"],
                "assertions": deleted["scenario"]["assertions"],
            },
        )
        gone = await _refused(client, "pack_scenario_delete", {**base, "id": "nope"})

    assert created["scenario"]["name"] == {"ru": "Сценарий агента", "en": "Сценарий агента"}
    assert taken["code"] == "scenario_taken"
    assert "if_match" in taken["hint"]
    assert [s["id"] for s in listed["scenarios"]] == ["agent-one"]
    assert edited["scenario"]["inputs"] == {"kind": "project"}
    assert edited["scenario"]["snapshot"] is not None
    assert edited["etag"] != etag
    assert stale["code"] == "stale_file"
    assert (run["passed"], run["failed"], run["errors"]) == (1, 0, 0)
    assert run["coverage"]["scenarios"] == 1
    assert "совпало 1" in run_text
    assert "Покрытие правил" in run_text
    assert [r["scenario"] for r in matrix["rows"]] == ["agent-one"]
    assert "agent-one" in matrix_text
    assert missing["code"] == "scenario_not_found"
    assert deleted["deleted"] is True
    assert deleted["scenario"]["inputs"] == {"kind": "project"}
    assert restored["scenario"]["name"]["ru"] == "Сценарий агента"
    assert gone["code"] == "scenario_not_found"


async def test__outcome__atlas_pin_limit_and_explain_with_counterfactuals(studio: Studio) -> None:
    async with _client(studio) as client:
        _, ws = await _connect(studio, client)
        atlas_text = await _text(client, "pack_outcome_atlas", {"workspace_id": ws, "version": _DRAFT, "limit": 3})
        atlas = await _json(
            client, "pack_outcome_atlas", {"workspace_id": ws, "version": _DRAFT, "limit": 2, "rows": 3}
        )
        pinned = await _json(
            client, "pack_outcome_atlas", {"workspace_id": ws, "version": _DRAFT, "pin": {"kind": "research"}}
        )
        bad_pin = await _refused(
            client, "pack_outcome_atlas", {"workspace_id": ws, "version": _DRAFT, "pin": {"nope": "x"}}
        )
        model = await _json(client, "pack_model", {"workspace_id": ws, "version": _DRAFT})
        doc = model["documents"][0]["id"]
        explained = await _text(
            client,
            "pack_outcome_explain",
            {"workspace_id": ws, "version": _DRAFT, "element": {"section": "documents", "id": doc}},
        )
        explained_json = await _json(
            client,
            "pack_outcome_explain",
            {"workspace_id": ws, "version": _DRAFT, "element": {"section": "documents", "id": doc}},
        )
        missing = await _refused(
            client,
            "pack_outcome_explain",
            {"workspace_id": ws, "version": _DRAFT, "element": {"section": "documents", "id": "no-such"}},
        )
        bad_element = await client.call_tool(
            "pack_outcome_explain", {"workspace_id": ws, "version": _DRAFT, "element": {"section": "x", "id": "y"}}
        )

    assert "измерений" in atlas_text
    assert "Группы исходов" in atlas_text
    assert atlas["outcomes_distinct"] >= 1
    assert len(atlas["outcomes"]) <= 2
    assert len(atlas["rows"]) <= 3
    assert pinned["rows_total"] <= atlas["rows_total"]
    assert bad_pin["code"] == "inputs_invalid"
    assert doc is not None
    assert explained.startswith(f"documents:{doc}")
    assert "chain" in explained_json
    assert missing["code"] == "outcome_element_not_found"
    assert bad_element.is_error is True


# ── git по шагам и полный цикл ───────────────────────────────────────────────


async def test__git__branch_commit_diff_checks_merge_and_start_over(studio: Studio) -> None:
    tex = f"{_DRAFT_DIR}/files/report/new.tex"
    async with _client(studio) as client:
        remote, ws = await _connect(studio, client)
        branches = await _json(client, "pack_git_branches", {"workspace_id": ws})
        bad_name = await _refused(client, "pack_git_branch", {"workspace_id": ws, "name": "bad name!"})
        base_branch = await _refused(client, "pack_git_branch", {"workspace_id": ws, "name": "main"})
        await _json(client, "pack_write_file", {"workspace_id": ws, "path": tex, "content": "\\relax\n"})
        branch = await _json(client, "pack_git_branch", {"workspace_id": ws, "name": "feature/steps"})
        committed = await _json(client, "pack_git_commit", {"workspace_id": ws, "message": "feat(packs): шаг агента"})
        again = await _json(client, "pack_git_commit", {"workspace_id": ws})
        diff = await _json(client, "pack_git_diff", {"workspace_id": ws})
        diff_text = await _text(client, "pack_git_diff", {"workspace_id": ws, "files_only": True})
        checks = await _json(client, "pack_git_checks", {"workspace_id": ws})
        merged = await _json(client, "pack_git_merge_base", {"workspace_id": ws})
        await _json(client, "pack_write_file", {"workspace_id": ws, "path": tex, "content": "\\relax\n% 2\n"})
        dirty_merge = await _refused(client, "pack_git_merge_base", {"workspace_id": ws})
        preview = await _json(client, "pack_git_start_over", {"workspace_id": ws})
        unsaved = await _refused(client, "pack_git_start_over", {"workspace_id": ws, "confirm": True})
        over = await _json(client, "pack_git_start_over", {"workspace_id": ws, "confirm": True, "discard": True})
        after = await _json(client, "pack_git_branches", {"workspace_id": ws})
        content = await _json(client, "pack_read_file", {"workspace_id": ws, "path": tex}, ok=False)

    assert branches["current"] is None
    assert branches["base"] == "main"
    assert bad_name["code"] == "branch_name_invalid"
    assert base_branch["code"] == "branch_name_invalid"
    assert branch["branch"] == "feature/steps"
    assert committed["committed"] is True
    assert committed["git"]["ahead"] == 1
    assert again["committed"] is False
    assert [tex] == [f.split(" ", 1)[1] for f in diff["files"]]
    assert "+\\relax" in diff["diff"]
    assert diff_text.startswith("Изменено файлов: 1")
    assert checks["pre_propose"]["errors"] == 0
    assert checks["ci"]["state"] in {"none", "pending", "success", "failure"}
    assert merged["branch"] == "feature/steps"
    assert dirty_merge["code"] == "workspace_dirty"
    assert "pack_git_commit" in dirty_merge["hint"]
    assert preview["confirm_required"] is True
    assert preview["unsaved_files"] == [tex]
    assert unsaved["code"] == "workspace_dirty"
    assert over["branch"] is None
    assert after["current"] is None
    assert content["code"] == "file_not_found"
    assert remote.head("main")


async def test__agent_cycle__new_template_branch_edit_lint_outcome_scenario_commit_propose(studio: Studio) -> None:
    async with _client(studio) as client:
        remote, ws = await _connect(studio, client)
        helped = await _text(client, "pack_help", {"topic": "flow"})
        branch = await _json(client, "pack_git_branch", {"workspace_id": ws, "name": "agent/new-template"})
        created = await _json(
            client,
            "pack_new_template",
            {
                "workspace_id": ws,
                "pack": "hse-cs-se",
                "template_id": "agent-report",
                "template_name": {"ru": "Отчёт агента", "en": "Agent report"},
                "version": "2026.1",
            },
        )
        version_path = created["version"]
        ref = "/".join(version_path.replace("/templates/", "/").replace("/versions/", "/").split("/"))
        manifest = f"{version_path}/version.yaml"
        model = await _json(client, "pack_model", {"workspace_id": ws, "version": ref})
        patched = await _json(
            client,
            "pack_patch_yaml",
            {
                "workspace_id": ws,
                "path": manifest,
                "if_match": model["manifest"]["etag"],
                "ops": [{"op": "set", "pointer": "/summary/ru", "value": "Отчёт, собранный агентом."}],
            },
        )
        lint = await _json(client, "pack_lint", {"workspace_id": ws, "path": version_path})
        outcome = await _text(client, "pack_outcome", {"workspace_id": ws, "version": ref})
        scenario = await _json(
            client,
            "pack_scenario_write",
            {
                "workspace_id": ws,
                "template": "hse-cs-se/agent-report",
                "id": "basic",
                "name": "Базовый",
                "record_snapshot": "work_tree",
                "version": "2026.1",
            },
        )
        run = await _json(
            client, "pack_scenario_run", {"workspace_id": ws, "template": "hse-cs-se/agent-report", "version": "2026.1"}
        )
        committed = await _json(
            client, "pack_git_commit", {"workspace_id": ws, "message": "feat(packs): шаблон агента"}
        )
        impact = await _text(client, "pack_outcome_impact", {"workspace_id": ws, "version": ref}, ok=False)
        checks = await _json(client, "pack_git_checks", {"workspace_id": ws, "ci": False})
        summary = await _json(client, "pack_propose", {"workspace_id": ws})
        proposed = await _json(client, "pack_propose", {"workspace_id": ws, "confirm": True})
        status = await _json(client, "pack_git_status", {"workspace_id": ws})

    assert "pack_propose" in helped
    assert branch["branch"] == "agent/new-template"
    assert created["pack_created"] is False
    assert patched["ops"] == 1
    assert lint["errors"] == 0, lint["findings"]
    assert outcome.startswith(ref)
    assert scenario["scenario"]["snapshot"] is not None
    assert (run["passed"], run["failed"], run["errors"]) == (1, 0, 0)
    assert committed["committed"] is True
    assert "diff_base_unavailable" in impact
    assert checks["pre_propose"]["errors"] == 0
    assert summary["confirm_required"] is True
    assert proposed["pushed_sha"] == remote.head("agent/new-template")
    assert proposed["checks"]["errors"] == 0
    assert status["branch"] == "agent/new-template"
    paths = remote.git("ls-tree", "-r", "--name-only", "refs/heads/agent/new-template")
    assert "packs/hse-cs-se/templates/agent-report/scenarios/basic.yaml" in paths
    assert f"packs/{manifest}" in paths
