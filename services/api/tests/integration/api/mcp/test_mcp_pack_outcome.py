"""MCP: результат версии шаблона `pack_outcome_inputs` и `pack_outcome` (template-studio-outcome.md, 4.7, срез O3).

Клиент SDK против локальной Студии, настоящий DI и служба результата. Версии настоящие (ВКР `hse-cs-se` 2026.1.2,
курсовой проект `hse-cs-sse` 2026.1.6, черновик ВКР 2026.1.9); три состояния версии читаются из git пространства.
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx2
import pytest
import pytest_asyncio
from fastapi import FastAPI
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.mcp_server import install_mcp
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService
from httpx import ASGITransport, AsyncClient
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client

from tests.fixtures.app import create_test_app, create_test_container
from tests.integration.api.pack_studio.conftest import Stand
from tests.integration.api.pack_studio.outcome_support import (
    COURSEWORK,
    DRAFT_VKR,
    LANGS,
    REAL_PACKS,
    VKR,
    copy_real_packs,
    edit_manifest,
)
from tests.integration.api.pack_studio.test_git_workspace import _git_workspace
from tests.integration.api.pack_studio.test_outcome_git import _PROFILE, _packs_remote

_BASE = "http://127.0.0.1"
TODAY = date(2026, 11, 16)


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
    service = await container.get(PackOutcomeService)
    monkeypatch.setattr(service, "_today", lambda: TODAY)
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url=_BASE) as rest:
            resp = await rest.put("/api/v1/mcp/settings", json={"enabled": True})
            assert resp.status_code == 200, resp.text
            yield Studio(app=app, stand=Stand(rest, tmp_path, container))
    finally:
        await container.close()
        app_settings.pack_studio = saved


async def _folder(studio: Studio) -> str:
    """Пространство-папка с настоящими версиями ВКР и курсового проекта."""
    await studio.stand.enable()
    root = copy_real_packs(studio.stand.root / "packs")
    ws = await studio.stand.folder_workspace(root.parent, packs_path=root.name)
    return str(ws["id"])


async def _git(studio: Studio) -> str:
    """Пространство над git: настоящие версии и черновик ВКР 2026.1.9, который можно править."""
    remote = _packs_remote(studio.stand.root)
    resp = await studio.rest.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    ws = await _git_workspace(studio.stand, remote)
    assert ws["state"] == "ready", ws
    return str(ws["id"])


def _client(studio: Studio) -> Client:
    http = httpx2.AsyncClient(transport=httpx2.ASGITransport(app=studio.app), base_url=_BASE)
    return Client(streamable_http_client(f"{_BASE}/mcp", http_client=http), mode="legacy")


def _ref(ref: tuple[str, str, str]) -> str:
    return "/".join(ref)


async def _text(client: Client, name: str, args: dict[str, Any], *, ok: bool = True) -> str:
    result = await client.call_tool(name, args)
    text = result.content[0].text  # type: ignore[union-attr]
    assert result.is_error is (not ok), text
    return str(text)


async def _json(client: Client, name: str, args: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    return dict(json.loads(await _text(client, name, args, ok=ok)))


async def _outcome(client: Client, ws: str, ref: tuple[str, str, str], **extra: Any) -> str:
    return await _text(client, "pack_outcome", {"workspace_id": ws, "version": _ref(ref), **extra})


def _core(ref: tuple[str, str, str], inputs: dict[str, str] | None = None, **kw: Any) -> dict[str, Any]:
    """Результат ядра на тех же файлах: с ним сверяется то, что показал тул."""
    version = YamlTemplateRepository(REAL_PACKS.parent / "packs").get_version(*ref)
    assert version is not None
    return dict(to_json(resolve(version, inputs or {}, auto_examples(version)[0], TODAY, **kw)))


def _active_in_text(text: str) -> set[str]:
    return set(re.findall(r"^  \+ ([\w-]+):", text, flags=re.MULTILINE))


# ── видимость и права ────────────────────────────────────────────────────────


async def test__list_tools__outcome_tools_follow_the_section_and_are_read_only(studio: Studio) -> None:
    async with _client(studio) as client:
        closed = {t.name for t in (await client.list_tools()).tools}
    await studio.stand.enable()
    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert not {"pack_outcome", "pack_outcome_inputs"} & closed
    for name in ("pack_outcome", "pack_outcome_inputs"):
        assert tools[name].annotations is not None
        assert tools[name].annotations.read_only_hint is True
        assert "project_id" not in tools[name].input_schema["properties"]
    props = tools["pack_outcome"].input_schema["properties"]
    assert {"workspace_id", "version", "state", "example", "inputs", "include", "detail", "trace", "format"} <= set(
        props
    )
    assert tools["pack_outcome"].input_schema["required"] == ["workspace_id", "version"]


@pytest.mark.parametrize("name", ["pack_outcome", "pack_outcome_inputs"])
async def test__call__section_closed__pack_studio_refusal(studio: Studio, name: str) -> None:
    async with _client(studio) as client:
        body = await _json(
            client, name, {"workspace_id": "00000000-0000-0000-0000-000000000000", "version": "a/b/c"}, ok=False
        )

    assert body["code"] == "pack_studio_disabled"


# ── словарь вводных ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", [VKR, COURSEWORK], ids=lambda r: r[1])
async def test__inputs__real_version__ids_values_defaults_and_examples(
    studio: Studio, ref: tuple[str, str, str]
) -> None:
    ws = await _folder(studio)

    async with _client(studio) as client:
        body = await _json(client, "pack_outcome_inputs", {"workspace_id": ws, "version": _ref(ref)})

    assert body["version"] == _ref(ref)
    assert body["state"] == "work_tree"
    assert body["default_example"] == "auto:normal"
    assert {e["id"] for e in body["examples"]} >= {"auto:normal", "auto:long", "auto:empty"}
    by_id = {i["id"]: i for i in body["inputs"]}
    assert {"kind", "staffing", "supervisor"} <= set(by_id)
    for item in body["inputs"]:
        assert item["default"] in item["values"], item["id"]
        assert set(item["affects"]) <= {"documents", "meta", "forms", "participants", "points", "route", "checks"}
    # Умолчания совпадают с вводными, которые считает расчёт без запроса.
    assert {i["id"]: i["default"] for i in body["inputs"]}.items() <= _core(ref)["inputs"].items()


async def test__inputs__refused_state_and_unknown_version(studio: Studio) -> None:
    ws = await _folder(studio)

    async with _client(studio) as client:
        no_git = await _json(
            client, "pack_outcome_inputs", {"workspace_id": ws, "version": _ref(VKR), "state": "head"}, ok=False
        )
        missing = await _json(
            client, "pack_outcome_inputs", {"workspace_id": ws, "version": "hse-cs-se/vkr/9.9.9"}, ok=False
        )

    assert (no_git["code"], no_git["reason"]) == ("diff_base_unavailable", "no_git")
    assert "work_tree" in no_git["hint"]
    assert missing["code"] == "version_not_found"


# ── результат ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref", [VKR, COURSEWORK], ids=lambda r: r[1])
async def test__outcome__default_compact_text__bundle_people_points_routes_and_no_noise(
    studio: Studio, ref: tuple[str, str, str]
) -> None:
    ws = await _folder(studio)
    expected = _core(ref)

    async with _client(studio) as client:
        text = await _outcome(client, ws, ref)

    lines = text.splitlines()
    assert lines[0].startswith(f"{_ref(ref)} [work_tree]")
    assert f"fingerprint {expected['fingerprint']}" in lines[0]
    assert "Вводные: все по умолчанию" in text
    for head in ("Сводка:", "Документы:", "Участники:", "Точки сдачи:", "Маршруты подписания:"):
        assert head in text, head
    # Что в комплекте по тексту, то и по ядру; итоговые имена файлов на месте.
    active = {d["id"] for d in expected["documents"] if d["state"] == "active"}
    assert _active_in_text(text) == active
    names = [
        i["file_name"]
        for d in expected["documents"]
        if d["state"] == "active"
        for i in d["instances"]
        if i["file_name"]
    ]
    assert names
    assert all(name in text for name in names)
    # Не запрошенное не приходит: поля, анкеты, проверки, ветки, трасса.
    for absent in ("Поля проекта:", "Анкеты:", "Проверки:", "Что если", "Трасса", "[t1"):
        assert absent not in text, absent
    assert "Предупреждени" in text


async def test__outcome__inputs_change_the_result_and_are_echoed(studio: Studio) -> None:
    ws = await _folder(studio)
    inputs = {"kind": "research", "staffing": "team2", "meta.nda": True}

    async with _client(studio) as client:
        default = await _outcome(client, ws, VKR, format="json")
        changed = await _outcome(client, ws, VKR, inputs=inputs, format="json")
        text = await _outcome(client, ws, VKR, inputs=inputs)

    default_data, changed_data = json.loads(default), json.loads(changed)
    assert changed_data["fingerprint"] != default_data["fingerprint"]
    assert changed_data["inputs"]["kind"] == "research"
    assert changed_data["inputs"]["staffing"] == "team2"
    # true из JSON это yes, как значение логической вводной.
    assert changed_data["inputs"]["meta.nda"] == "yes"
    expected = _core(VKR, {"kind": "research", "staffing": "team2", "meta.nda": "yes"})
    assert changed_data["fingerprint"] == expected["fingerprint"]
    assert changed_data["summary"]["documents"] == sum(1 for d in expected["documents"] if d["state"] == "active")
    assert "Вводные заданы: kind=research, staffing=team2, meta.nda=yes; остальные по умолчанию" in text
    # Личные документы команды по участникам: у двоих два экземпляра с author1 и author2.
    assert "author1:" in text
    assert "author2:" in text


async def test__outcome__scenario_argument_puts_its_inputs_between_the_defaults_and_inputs(studio: Studio) -> None:
    ws = await _folder(studio)
    folder = studio.stand.root / "packs" / "hse-cs-se" / "templates" / "vkr" / "scenarios"
    folder.mkdir()
    (folder / "research-team.yaml").write_text(
        "format: 1\nname:\n  ru: Команда, исследование\ninputs:\n  kind: research\n  staffing: team2\n",
        encoding="utf-8",
    )

    async with _client(studio) as client:
        plain = json.loads(await _outcome(client, ws, VKR, format="json"))
        scenario = json.loads(await _outcome(client, ws, VKR, scenario="research-team", format="json"))
        over = json.loads(
            await _outcome(client, ws, VKR, scenario="research-team", inputs={"staffing": "solo"}, format="json")
        )
        listed = await _json(
            client, "pack_outcome_inputs", {"workspace_id": ws, "version": _ref(VKR), "scenario": "research-team"}
        )
        ghost = await _text(
            client, "pack_outcome", {"workspace_id": ws, "version": _ref(VKR), "scenario": "ghost"}, ok=False
        )

    assert (plain["inputs"]["kind"], plain["inputs"]["staffing"]) == ("project", "solo")
    assert (scenario["inputs"]["kind"], scenario["inputs"]["staffing"]) == ("research", "team2")
    assert (over["inputs"]["kind"], over["inputs"]["staffing"]) == ("research", "solo")
    expected = _core(VKR, {"kind": "research", "staffing": "team2"})
    assert scenario["fingerprint"] == expected["fingerprint"]
    assert listed["inputs"]
    assert "scenarios/<id>.yaml" in ghost or "scenario" in ghost


async def test__outcome__inactive_documents_come_with_the_reason(studio: Studio) -> None:
    ws = await _folder(studio)

    async with _client(studio) as client:
        text = await _outcome(client, ws, VKR)

    off = [line for line in text.splitlines() if line.startswith("  - ")]
    assert off, text
    # Причина это первое невыполненное условие: правило, условие и фактическое значение.
    assert any("(" in line and " in [" in line or " = " in line for line in off), off


async def test__outcome__include_picks_sections__expensive_ones_only_on_request(studio: Studio) -> None:
    ws = await _folder(studio)

    async with _client(studio) as client:
        only_meta = await _outcome(client, ws, COURSEWORK, include=["meta"])
        listed = await _outcome(client, ws, COURSEWORK, include="forms,route")
        everything = await _outcome(client, ws, COURSEWORK, include=["all"])

    assert "Поля проекта:" in only_meta
    assert "Документы:" not in only_meta
    assert "Сводка:" in only_meta
    assert "Анкеты:" in listed
    assert "Маршруты подписания:" in listed
    assert "Участники:" not in listed
    for head in (
        "Документы:",
        "Поля проекта:",
        "Анкеты:",
        "Участники:",
        "Точки сдачи:",
        "Маршруты подписания:",
        "Проверки:",
        "Что если сменить вводную:",
    ):
        assert head in everything, head
    assert "не посчитаны" not in everything


async def test__outcome__trace__only_decisions_behind_the_shown_elements(studio: Studio) -> None:
    ws = await _folder(studio)
    expected = _core(VKR)

    async with _client(studio) as client:
        text = await _outcome(client, ws, VKR, include=["documents"], trace=True)
        data = json.loads(await _outcome(client, ws, VKR, include=["documents"], trace=True, format="json"))
        plain = json.loads(await _outcome(client, ws, VKR, include=["documents"], format="json"))
        plain_text = await _outcome(client, ws, VKR, include=["documents"])

    docs_why = {t for d in expected["documents"] for t in [*d["why"], *(w for v in d["variants"] for w in v["why"])]}
    assert docs_why
    assert {e["id"] for e in data["trace"]} == docs_why
    assert len(data["trace"]) < len(expected["trace"])
    assert "Трасса (" in text
    for trace_id in list(docs_why)[:3]:
        assert f"  {trace_id} " in text
    # Решение с правилом, условием и фактами; ссылка на элементы.
    first = text.split("Трасса (")[1].splitlines()[1]
    assert re.search(r"t\d+ (held|not_held|skipped) (gate|exclude|add|order|display|require) \w+: ", first), first
    assert "files/" in text or "builtin:" in text
    assert "trace" not in plain
    assert not re.search(r"\[t\d+(,t\d+)*\]", plain_text)


async def test__outcome__detail_and_format__full_is_richer_and_compact_is_smaller(studio: Studio) -> None:
    ws = await _folder(studio)

    async with _client(studio) as client:
        compact = await _outcome(client, ws, VKR, include=["all"])
        full = await _outcome(client, ws, VKR, include=["all"], detail="full")
        compact_json = await _outcome(client, ws, VKR, include=["all"], format="json")
        full_json = await _outcome(client, ws, VKR, include=["all"], detail="full", format="json")
        both = json.loads(await _outcome(client, ws, VKR, format="both"))

    assert len(full) > len(compact)
    assert "Не входит в результат:" in full
    assert "Не входит в результат:" not in compact
    assert "Вводные: " in full
    assert len(compact_json) < len(full_json) / 2
    assert len(compact) < len(full_json) / 4
    full_data = json.loads(full_json)
    assert set(full_data["sections"]) == {
        "documents",
        "meta",
        "forms",
        "participants",
        "points",
        "route",
        "checks",
        "branches",
    }
    assert full_data["out_of_scope"]
    assert "why" not in json.dumps(full_data["sections"])
    assert set(both) == {"text", "data"}
    assert both["text"].startswith(f"{_ref(VKR)} [work_tree]")
    assert both["data"]["version"] == _ref(VKR)


async def test__outcome__supervisor_none__step_without_person_is_a_warning(studio: Studio) -> None:
    ws = await _folder(studio)

    async with _client(studio) as client:
        text = await _outcome(client, ws, VKR, inputs={"supervisor": "none"})
        data = json.loads(await _outcome(client, ws, VKR, inputs={"supervisor": "none"}, format="json"))

    codes = {w["code"] for w in data["warnings"]}
    assert "step_without_person" in codes
    assert "Предупреждения (" in text
    assert "ждёт «supervisor»" in text


# ── ошибки ───────────────────────────────────────────────────────────────────


async def test__outcome__inputs_invalid__field_value_reason_and_a_hint(studio: Studio) -> None:
    ws = await _folder(studio)

    async with _client(studio) as client:
        unknown = await _json(
            client, "pack_outcome", {"workspace_id": ws, "version": _ref(VKR), "inputs": {"nope": "x"}}, ok=False
        )
        value = await _json(
            client, "pack_outcome", {"workspace_id": ws, "version": _ref(VKR), "inputs": {"kind": "zzz"}}, ok=False
        )
        example = await _json(
            client, "pack_outcome", {"workspace_id": ws, "version": _ref(VKR), "example": "nope"}, ok=False
        )

    for body, field in ((unknown, "nope"), (value, "kind"), (example, "example")):
        assert body["code"] == "inputs_invalid", body
        assert body["field"] == field
        assert body["reason"]
        assert "pack_outcome_inputs" in body["hint"]
    assert value["value"] == "zzz"


async def test__outcome__bad_arguments__are_refused_with_a_clear_message(studio: Studio) -> None:
    ws = await _folder(studio)
    base = {"workspace_id": ws, "version": _ref(VKR)}
    cases = {
        "state": {"state": "tail"},
        "include": {"include": ["documents", "bogus"]},
        "detail": {"detail": "huge"},
        "format": {"format": "xml"},
        "inputs": {"inputs": ["kind"]},
    }

    async with _client(studio) as client:
        for key, extra in cases.items():
            result = await client.call_tool("pack_outcome", {**base, **extra})
            assert result.is_error is True, key
            assert key in result.content[0].text, result.content[0].text  # type: ignore[union-attr]
        too_long = await client.call_tool("pack_outcome", {**base, "inputs": {"kind": "x" * 200}})
        not_a_version = await client.call_tool("pack_outcome", {"workspace_id": ws, "version": "vkr"})

    assert too_long.is_error is True
    assert not_a_version.is_error is True


async def test__outcome__unknown_workspace_and_version(studio: Studio) -> None:
    ws = await _folder(studio)

    async with _client(studio) as client:
        missing = await _json(client, "pack_outcome", {"workspace_id": ws, "version": "hse-cs-se/vkr/9.9.9"}, ok=False)
        alien = await _json(
            client,
            "pack_outcome",
            {"workspace_id": "11111111-1111-1111-1111-111111111111", "version": _ref(VKR)},
            ok=False,
        )

    assert missing["code"] == "version_not_found"
    assert alien["code"] == "workspace_not_found"


# ── три состояния ────────────────────────────────────────────────────────────


async def test__states__unsaved_edit_is_seen_in_work_tree_only__head_and_base_keep_the_old(studio: Studio) -> None:
    ws = await _git(studio)

    async with _client(studio) as client:
        clean = [await _outcome(client, ws, DRAFT_VKR, state=s, format="json") for s in ("work_tree", "head", "base")]
        await edit_manifest(studio.stand, ws, LANGS, "langs: [ru]")
        work = await _json(client, "pack_outcome_inputs", {"workspace_id": ws, "version": _ref(DRAFT_VKR)})
        head = await _json(
            client, "pack_outcome_inputs", {"workspace_id": ws, "version": _ref(DRAFT_VKR), "state": "head"}
        )
        base = await _json(
            client, "pack_outcome_inputs", {"workspace_id": ws, "version": _ref(DRAFT_VKR), "state": "base"}
        )
        # Язык en есть у head и base, а в рабочем дереве правка его убрала.
        refused = await _json(
            client,
            "pack_outcome",
            {"workspace_id": ws, "version": _ref(DRAFT_VKR), "inputs": {"lang": "en"}},
            ok=False,
        )
        on_head = await _outcome(client, ws, DRAFT_VKR, state="head", inputs={"lang": "en"})

    assert {json.loads(c)["fingerprint"] for c in clean} == {json.loads(clean[0])["fingerprint"]}
    assert [json.loads(c)["state"] for c in clean] == ["work_tree", "head", "base"]
    lang = {
        s: next(i for i in b["inputs"] if i["id"] == "lang")["values"]
        for s, b in (("work", work), ("head", head), ("base", base))
    }
    assert lang == {"work": ["ru"], "head": ["ru", "en"], "base": ["ru", "en"]}
    assert (work["state"], head["state"], base["state"]) == ("work_tree", "head", "base")
    assert refused["code"] == "inputs_invalid"
    assert refused["field"] == "lang"
    assert "[head]" in on_head.splitlines()[0]


async def test__states__new_version_has_no_head_and_base__hint_says_what_to_do(studio: Studio) -> None:
    ws = await _git(studio)
    manifest = "hse-cs-se/templates/vkr/versions/2026.1.10/version.yaml"
    created = await studio.rest.put(
        studio.stand.file_url(ws, manifest), content=b'id: "2026.1.10"\nstatus: beta\nlangs: [ru]\n'
    )
    assert created.status_code == 200, created.text
    new = ("hse-cs-se", "vkr", "2026.1.10")

    async with _client(studio) as client:
        work = await _outcome(client, ws, new)
        head = await _json(
            client, "pack_outcome", {"workspace_id": ws, "version": _ref(new), "state": "head"}, ok=False
        )
        base = await _json(
            client, "pack_outcome", {"workspace_id": ws, "version": _ref(new), "state": "base"}, ok=False
        )

    assert "[work_tree]" in work.splitlines()[0]
    for body in (head, base):
        assert (body["code"], body["reason"]) == ("diff_base_unavailable", "new_version")
        assert "work_tree" in body["hint"]


async def test__states__head_and_base_equal_work_tree_on_a_clean_clone(studio: Studio) -> None:
    ws = await _git(studio)

    async with _client(studio) as client:
        for ref in (VKR, COURSEWORK):
            data = [
                json.loads(await _outcome(client, ws, ref, state=s, format="json", include=["all"]))
                for s in ("work_tree", "head", "base")
            ]
            assert [d["state"] for d in data] == ["work_tree", "head", "base"]
            assert data[0]["sections"] == data[1]["sections"] == data[2]["sections"]
