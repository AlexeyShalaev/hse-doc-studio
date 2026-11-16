"""MCP: сравнения результата `pack_outcome_compare` и `pack_outcome_impact` (template-studio-outcome.md, 4.5 и 4.7,
срез O7).

Клиент SDK против локальной Студии, настоящий DI и служба сравнений. Версии настоящие (курсовой проект `hse-cs-sse`
2026.1.6 и его черновик 2026.1.9, ВКР `hse-cs-se`), стартовые сценарии паков; состояния `head` и `base` читаются из git
пространства."""

from __future__ import annotations

import json
from typing import Any

from tests.integration.api.mcp.test_mcp_pack_outcome import (
    Studio,
    _client,
    _json,
    _ref,
    _text,
    studio,  # noqa: F401 — фикстура
)
from tests.integration.api.pack_studio.outcome_compare_support import (
    ANNOTATION_AFTER,
    ANNOTATION_BEFORE,
    DRAFT_ANNOTATION,
    DRAFT_COURSEWORK,
    DRAFT_COURSEWORK_MANIFEST,
    SLOT_AFTER,
    SLOT_BEFORE,
    edit_file,
    folder_with_scenarios,
)
from tests.integration.api.pack_studio.outcome_support import COURSEWORK, DRAFT_VKR
from tests.integration.api.pack_studio.test_git_workspace import _git_workspace
from tests.integration.api.pack_studio.test_outcome_compare_git import _PROFILE, _remote

_UNIVERSITY = {"supervisor": "university", "co_supervisor": "no"}
_COMPANY = {"supervisor": "company", "co_supervisor": "yes"}


async def _folder(studio_: Studio) -> str:
    ws, _ = await folder_with_scenarios(studio_.stand)
    return ws


async def _git(studio_: Studio) -> str:
    remote = _remote(studio_.stand.root)
    resp = await studio_.rest.put("/api/v1/profile", json=_PROFILE)
    assert resp.status_code == 200, resp.text
    ws = await _git_workspace(studio_.stand, remote)
    assert ws["state"] == "ready", ws
    return str(ws["id"])


async def test__list_tools__compare_tools_follow_the_section_and_are_read_only(studio: Studio) -> None:  # noqa: F811
    async with _client(studio) as client:
        closed = {t.name for t in (await client.list_tools()).tools}
    await studio.stand.enable()
    async with _client(studio) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

    assert not {"pack_outcome_compare", "pack_outcome_impact"} & closed
    for name in ("pack_outcome_compare", "pack_outcome_impact"):
        assert tools[name].annotations is not None
        assert tools[name].annotations.read_only_hint is True
        assert "project_id" not in tools[name].input_schema["properties"]
    compare = tools["pack_outcome_compare"].input_schema
    assert compare["required"] == ["workspace_id", "version", "left", "right"]
    assert {"left", "right", "state", "scenario", "inputs", "sections", "detail", "format"} <= set(
        compare["properties"]
    )
    impact = tools["pack_outcome_impact"].input_schema
    assert impact["required"] == ["workspace_id", "version"]
    assert impact["properties"]["base"]["enum"] == ["base", "head"]


async def test__call__section_closed__pack_studio_refusal(studio: Studio) -> None:  # noqa: F811
    args = {"workspace_id": "00000000-0000-0000-0000-000000000000", "version": "a/b/c"}
    async with _client(studio) as client:
        compare = await _json(client, "pack_outcome_compare", {**args, "left": {}, "right": {}}, ok=False)
        impact = await _json(client, "pack_outcome_impact", args, ok=False)

    assert compare["code"] == impact["code"] == "pack_studio_disabled"


# ── compare ──────────────────────────────────────────────────────────────────


async def test__compare__two_scenarios__text_names_changes_with_symbols_and_reasons(studio: Studio) -> None:  # noqa: F811
    ws = await _folder(studio)

    async with _client(studio) as client:
        text = await _text(
            client,
            "pack_outcome_compare",
            {
                "workspace_id": ws,
                "version": _ref(COURSEWORK),
                "left": {"scenario": "university-supervisor"},
                "right": {"scenario": "company-supervisor"},
            },
        )

    lines = text.splitlines()
    assert lines[0] == "Сравнение hse-cs-sse/coursework/2026.1.6"
    assert "left: work_tree, scenario university-supervisor" in text
    assert "right: work_tree, scenario company-supervisor" in text
    assert "Вводные различаются: supervisor: university -> company, co_supervisor: no -> yes" in text
    assert "Результаты различаются: participants +1 ~0 -0; route +3 ~1 -2" in text
    assert "  + участник co_supervisor" in text
    assert "  ~ topic-approval: шаг 2: supervisor -> supervisor, co_supervisor" in text
    assert "      why: slot_when:" in text
    assert "not_held -> held" in text
    assert "| hse-cs-sse" not in text  # файл правила называется относительно версии
    assert "version.yaml#/pack_submission/profiles/0/signing_slots/0/when" in text


async def test__compare__common_inputs_and_states__one_combination_before_and_after_an_edit(studio: Studio) -> None:  # noqa: F811
    ws = await _git(studio)
    await edit_file(studio.stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)

    async with _client(studio) as client:
        data = await _json(
            client,
            "pack_outcome_compare",
            {
                "workspace_id": ws,
                "version": _ref(DRAFT_COURSEWORK),
                "left": {"state": "base"},
                "right": {"state": "work_tree"},
                "inputs": _UNIVERSITY,
                "format": "json",
            },
        )
        same = await _text(
            client,
            "pack_outcome_compare",
            {
                "workspace_id": ws,
                "version": _ref(DRAFT_COURSEWORK),
                "left": {"state": "head", "inputs": _COMPANY},
                "right": {"inputs": _COMPANY},
            },
        )

    assert data["left"]["state"] == "base"
    assert data["right"]["state"] == "work_tree"
    assert data["identical"] is False
    assert {(c["symbol"], c["kind"]) for c in data["changes"]} == {
        ("+", "route_step"),
        ("+", "route_pair"),
        ("-", "skipped_pair"),
    }
    # В компактном виде у изменения одна главная причина.
    assert all(len(c["why"]) <= 1 for c in data["changes"])
    assert "Результаты совпадают: изменений нет." in same


async def test__compare__full_detail_sections_filter_and_both_format(studio: Studio) -> None:  # noqa: F811
    ws = await _folder(studio)
    args: dict[str, Any] = {
        "workspace_id": ws,
        "version": _ref(COURSEWORK),
        "left": {"inputs": _UNIVERSITY},
        "right": {"inputs": _COMPANY},
    }

    async with _client(studio) as client:
        participants = await _text(client, "pack_outcome_compare", {**args, "sections": ["participants"]})
        both = await _json(client, "pack_outcome_compare", {**args, "detail": "full", "format": "both"})

    assert "participants (+1 ~0 -0)" in participants
    assert "route (" not in participants
    assert set(both) == {"text", "data"}
    assert max(len(c["why"]) for c in both["data"]["changes"]) > 1
    assert "route (+3 ~1 -2)" in both["text"]


async def test__compare__refusals_carry_hints(studio: Studio) -> None:  # noqa: F811
    ws = await _folder(studio)
    base = {"workspace_id": ws, "version": _ref(COURSEWORK)}

    async with _client(studio) as client:
        bad = await _json(
            client,
            "pack_outcome_compare",
            {**base, "left": {}, "right": {"inputs": {"supervisor": "firm"}}},
            ok=False,
        )
        no_git = await _json(client, "pack_outcome_compare", {**base, "left": {"state": "base"}, "right": {}}, ok=False)
        ghost = await _json(
            client, "pack_outcome_compare", {**base, "left": {"scenario": "ghost"}, "right": {}}, ok=False
        )
        unknown = await _text(
            client, "pack_outcome_compare", {**base, "left": {"colour": "red"}, "right": {}}, ok=False
        )

    assert (bad["code"], bad["side"], bad["field"]) == ("inputs_invalid", "right", "supervisor")
    assert "pack_outcome_inputs" in bad["hint"]
    assert (no_git["code"], no_git["reason"]) == ("diff_base_unavailable", "no_git")
    assert "state=work_tree" in no_git["hint"]
    assert ghost["code"] == "scenario_not_found"
    assert "scenarios/<id>.yaml" in ghost["hint"]
    assert "colour" in str(unknown)


# ── impact ───────────────────────────────────────────────────────────────────


async def test__impact__after_a_slot_edit__n_of_m_scenarios_and_the_changes(studio: Studio) -> None:  # noqa: F811
    ws = await _git(studio)
    await edit_file(studio.stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)

    async with _client(studio) as client:
        text = await _text(
            client,
            "pack_outcome_impact",
            {"workspace_id": ws, "version": _ref(DRAFT_COURSEWORK), "include_atlas": True},
        )
        data = await _json(
            client, "pack_outcome_impact", {"workspace_id": ws, "version": _ref(DRAFT_COURSEWORK), "format": "json"}
        )

    assert "До и после hse-cs-sse/coursework/2026.1.9: base -> work_tree" in text
    assert "Изменится результат в 1 из 3 сценариев (без изменений 2, ошибок 0)" in text
    assert "Разделы: route +2 ~0 -1" in text
    assert "Атлас: изменилось" in text
    assert "university-supervisor: изменился" in text
    assert "company-supervisor: без изменений" in text
    assert "  + topic-approval: шаг 3: - -> academic_supervisor" in text
    assert "  - topic-approval: topic_application: academic_supervisor, условие не выполнено" in text
    assert data["summary"]["scenarios_changed"] == 1
    assert data["summary"]["atlas"] is None  # include_atlas по умолчанию выключен у тула
    assert {s["status"] for s in data["scenarios"]} == {"changed", "unchanged"}


async def test__impact__vkr_document_edit__sections_and_scenario_selection(studio: Studio) -> None:  # noqa: F811
    ws = await _git(studio)
    await edit_file(studio.stand, ws, DRAFT_ANNOTATION, ANNOTATION_BEFORE, ANNOTATION_AFTER)

    async with _client(studio) as client:
        text = await _text(client, "pack_outcome_impact", {"workspace_id": ws, "version": _ref(DRAFT_VKR)})
        picked = await _text(
            client,
            "pack_outcome_impact",
            {
                "workspace_id": ws,
                "version": _ref(DRAFT_VKR),
                "scenarios": ["team-of-three-nda"],
                "sections": ["documents"],
                "detail": "full",
            },
        )

    assert "Изменится результат в 1 из 4 сценариев" in text
    assert "+ документ shared_annotation: absent -> active" in text
    assert "Изменится результат в 1 из 1 сценариев" in picked
    assert "points" not in picked.split("team-of-three-nda: изменился", 1)[1]


async def test__impact__without_a_base__hint_says_what_to_do(studio: Studio) -> None:  # noqa: F811
    ws = await _folder(studio)

    async with _client(studio) as client:
        body = await _json(client, "pack_outcome_impact", {"workspace_id": ws, "version": _ref(COURSEWORK)}, ok=False)
        bad_scenarios = await _text(
            client,
            "pack_outcome_impact",
            {"workspace_id": ws, "version": _ref(COURSEWORK), "scenarios": [f"s{i}" for i in range(201)]},
            ok=False,
        )

    assert (body["code"], body["reason"]) == ("diff_base_unavailable", "no_git")
    assert "work_tree" in body["hint"]
    assert "не больше 200" in str(bad_scenarios) or "at most 200" in str(bad_scenarios)


async def test__impact__is_read_only_and_does_not_change_the_workspace(studio: Studio) -> None:  # noqa: F811
    ws = await _git(studio)
    await edit_file(studio.stand, ws, DRAFT_COURSEWORK_MANIFEST, SLOT_BEFORE, SLOT_AFTER)
    before = await studio.rest.get(f"/api/v1/pack-studio/workspaces/{ws}/git")

    async with _client(studio) as client:
        await _text(client, "pack_outcome_impact", {"workspace_id": ws, "version": _ref(DRAFT_COURSEWORK)})
        await _text(
            client,
            "pack_outcome_compare",
            {"workspace_id": ws, "version": _ref(DRAFT_COURSEWORK), "left": {"state": "base"}, "right": {}},
        )

    after = await studio.rest.get(f"/api/v1/pack-studio/workspaces/{ws}/git")
    assert json.dumps(after.json(), sort_keys=True) == json.dumps(before.json(), sort_keys=True)
