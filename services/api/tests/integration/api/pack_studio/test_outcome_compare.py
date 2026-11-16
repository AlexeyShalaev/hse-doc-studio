"""Сравнения результата по HTTP: `compare`, `impact` и `matrix` (template-studio-outcome.md, 4.5 и 4.6, срез O7) в
локальной Студии над папкой.

Настоящие роутер и DI, настоящие версии (ВКР `hse-cs-se` 2026.1.2, курсовой проект `hse-cs-sse` 2026.1.6) и стартовые
сценарии паков. Ответы принимают строгие модели контракта и равны независимому прямому расчёту (`resolve` двух
сторон). Состояния `head` и `base` над git: `test_outcome_compare_git.py`; MCP: `tests/integration/api/mcp`."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.pack_studio.outcome.scenarios import parse_scenario
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.compare import (
    Side,
    VersionSide,
    compare_body,
    compare_sides,
    matrix_body,
    matrix_rows,
)
from hse_doc_studio.use_cases.pack_studio.outcome_compare import CompareLimits, PackCompareService
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService

from .conftest import API, Stand
from .outcome_compare_support import (
    COURSEWORK,
    VKR,
    folder_with_scenarios,
    parse_compare,
    parse_matrix,
    post_op,
)
from .outcome_support import post_outcome
from .scenario_support import COURSEWORK_TEMPLATE, put_scenario, scenario_body, scenarios_url, tree_digest

TODAY = date(2026, 11, 16)
_UNIVERSITY = {"supervisor": "university", "co_supervisor": "no"}
_COMPANY = {"supervisor": "company", "co_supervisor": "yes"}


@pytest.fixture
async def services(stand: Stand, monkeypatch: pytest.MonkeyPatch) -> PackCompareService:
    """Службы стенда с зафиксированным днём (ключ кэша и значения по умолчанию зависят от него)."""
    assert stand.container is not None
    outcome = await stand.container.get(PackOutcomeService)
    monkeypatch.setattr(outcome, "_today", lambda: TODAY)
    return await stand.container.get(PackCompareService)


def _direct(root: Path, ref: tuple[str, str, str]) -> tuple[Any, Any]:
    version = YamlTemplateRepository(root).get_version(*ref)
    assert version is not None
    return version, auto_examples(version)[0]


def _scenarios(root: Path, ref: tuple[str, str, str]) -> dict[str, Any]:
    folder = root / ref[0] / "templates" / ref[1] / "scenarios"
    return {p.stem: parse_scenario(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.yaml"))}


# ── compare ──────────────────────────────────────────────────────────────────


async def test__compare__two_scenarios__strict_model_and_equal_to_a_direct_resolve(
    stand: Stand, services: PackCompareService
) -> None:
    ws, root = await folder_with_scenarios(stand)
    version, example = _direct(root, COURSEWORK)
    body = {
        "left": {"scenario": "university-supervisor"},
        "right": {"scenario": "company-supervisor"},
    }

    resp = await post_op(stand, ws, COURSEWORK, "compare", body)

    got = parse_compare(resp)
    scenarios = _scenarios(root, COURSEWORK)
    direct = compare_sides(
        Side(version, example, scenarios["university-supervisor"].inputs, got.left.revision),
        Side(version, example, scenarios["company-supervisor"].inputs, got.right.revision),
        TODAY,
    )
    assert resp.json() == {
        "workspace_id": ws,
        "pack": COURSEWORK[0],
        "template": COURSEWORK[1],
        "version": COURSEWORK[2],
        **compare_body(direct, "work_tree", "work_tree"),
    }
    assert not got.identical
    assert {(c.symbol, c.kind) for c in got.changes} >= {("+", "participant"), ("~", "route_step"), ("+", "route_pair")}
    assert [d.section for d in got.summary] == ["participants", "route"]
    assert got.left.inputs["supervisor"] == "university"
    assert got.right.inputs["supervisor"] == "company"
    assert any(r.kind == "slot_when" for c in got.changes for r in c.why)


async def test__compare__inputs_over_a_scenario_and_the_same_side_twice(
    stand: Stand, services: PackCompareService
) -> None:
    ws, _ = await folder_with_scenarios(stand)

    same = parse_compare(
        await post_op(
            stand,
            ws,
            COURSEWORK,
            "compare",
            {"left": {"inputs": _UNIVERSITY}, "right": {"scenario": "university-supervisor"}},
        )
    )
    override = parse_compare(
        await post_op(
            stand,
            ws,
            COURSEWORK,
            "compare",
            {
                "left": {"scenario": "university-supervisor"},
                "right": {"scenario": "university-supervisor", "inputs": {"co_supervisor": "yes"}},
            },
        )
    )

    assert same.identical
    assert same.changes == []
    assert same.left.fingerprint == same.right.fingerprint
    assert not override.identical
    assert [c.id for c in override.changes if c.section == "participants"] == ["co_supervisor"]


async def test__compare__etag_is_stable_and_follows_the_request(stand: Stand, services: PackCompareService) -> None:
    ws, _ = await folder_with_scenarios(stand)
    body = {"left": {"inputs": _UNIVERSITY}, "right": {"inputs": _COMPANY}}

    first = await post_op(stand, ws, COURSEWORK, "compare", body)
    again = await post_op(stand, ws, COURSEWORK, "compare", body, **{"If-None-Match": first.headers["ETag"]})
    weak = await post_op(stand, ws, COURSEWORK, "compare", body, **{"If-None-Match": f"W/{first.headers['ETag']}"})
    other = await post_op(stand, ws, COURSEWORK, "compare", {"left": body["right"], "right": body["left"]})

    assert first.status_code == 200
    assert first.headers["Cache-Control"] == "private, no-cache"
    assert (again.status_code, weak.status_code) == (304, 304)
    assert again.content == b""
    assert other.headers["ETag"] != first.headers["ETag"]


async def test__compare__second_request_is_cached_and_computes_nothing(
    stand: Stand, services: PackCompareService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, _ = await folder_with_scenarios(stand)
    body = {"left": {"inputs": _UNIVERSITY}, "right": {"inputs": _COMPANY}}
    first = await post_op(stand, ws, COURSEWORK, "compare", body)
    from hse_doc_studio.use_cases.pack_studio import outcome_compare  # noqa: PLC0415

    def boom(*_: Any, **__: Any) -> Any:
        raise AssertionError("the comparison must come from the cache")

    monkeypatch.setattr(outcome_compare, "compare_sides", boom)

    second = await post_op(stand, ws, COURSEWORK, "compare", body)

    assert second.status_code == 200
    assert second.json() == first.json()


async def test__compare__bad_inputs_name_the_side(stand: Stand, services: PackCompareService) -> None:
    ws, _ = await folder_with_scenarios(stand)

    right = await post_op(stand, ws, COURSEWORK, "compare", {"left": {}, "right": {"inputs": {"supervisor": "firm"}}})
    left = await post_op(stand, ws, COURSEWORK, "compare", {"left": {"inputs": {"nope": "x"}}, "right": {}})

    assert right.status_code == 400
    assert {k: right.json()[k] for k in ("code", "field", "value", "side")} == {
        "code": "inputs_invalid",
        "field": "supervisor",
        "value": "firm",
        "side": "right",
    }
    assert (left.status_code, left.json()["side"], left.json()["field"]) == (400, "left", "nope")


async def test__compare__unknown_scenario_version_and_workspace(stand: Stand, services: PackCompareService) -> None:
    ws, _ = await folder_with_scenarios(stand)

    scenario = await post_op(stand, ws, COURSEWORK, "compare", {"left": {"scenario": "ghost"}, "right": {}})
    version = await post_op(stand, ws, ("hse-cs-sse", "coursework", "9.9.9"), "compare", {"left": {}, "right": {}})
    workspace = await post_op(
        stand, "00000000-0000-0000-0000-000000000000", COURSEWORK, "compare", {"left": {}, "right": {}}
    )

    assert (scenario.status_code, scenario.json()["code"]) == (404, "scenario_not_found")
    assert (version.status_code, version.json()["code"]) == (404, "version_not_found")
    assert (workspace.status_code, workspace.json()["code"]) == (404, "workspace_not_found")


async def test__compare__folder_has_no_head_and_base__diff_base_unavailable(
    stand: Stand, services: PackCompareService
) -> None:
    ws, _ = await folder_with_scenarios(stand)

    for state in ("head", "base"):
        left = await post_op(stand, ws, COURSEWORK, "compare", {"left": {"state": state}, "right": {}})
        right = await post_op(stand, ws, COURSEWORK, "compare", {"left": {}, "right": {"state": state}})
        for resp in (left, right):
            assert resp.status_code == 409, resp.text
            assert resp.json()["code"] == "diff_base_unavailable"
            assert resp.json()["reason"] == "no_git"


async def test__compare__request_shape__unknown_field_and_state_are_validation_errors(
    stand: Stand, services: PackCompareService
) -> None:
    ws, _ = await folder_with_scenarios(stand)

    unknown = await post_op(stand, ws, COURSEWORK, "compare", {"left": {"colour": "red"}, "right": {}})
    state = await post_op(stand, ws, COURSEWORK, "compare", {"left": {"state": "tail"}, "right": {}})
    missing = await post_op(stand, ws, COURSEWORK, "compare", {"left": {}})

    assert (unknown.status_code, state.status_code, missing.status_code) == (422, 422, 422)


async def test__compare__vkr_team_against_solo(stand: Stand, services: PackCompareService) -> None:
    ws, _ = await folder_with_scenarios(stand)

    got = parse_compare(
        await post_op(
            stand,
            ws,
            VKR,
            "compare",
            {
                "left": {"scenario": "solo-university-supervisor"},
                "right": {"scenario": "team-of-three-nda"},
            },
        )
    )

    assert {(c.symbol, c.id) for c in got.changes if c.kind == "document"} >= {
        ("+", "shared_technical_specification"),
        ("+", "nda"),
    }
    assert {c.id for c in got.changes if c.kind == "participant"} >= {"author1", "author2", "author3"}
    assert got.summary[0].section == "documents"


# ── impact ───────────────────────────────────────────────────────────────────


async def test__impact__folder_has_no_base__diff_base_unavailable_with_the_reason(
    stand: Stand, services: PackCompareService
) -> None:
    ws, _ = await folder_with_scenarios(stand)

    for base in ("base", "head"):
        resp = await post_op(stand, ws, COURSEWORK, "impact", {"base": base})
        assert resp.status_code == 409, resp.text
        assert (resp.json()["code"], resp.json()["reason"]) == ("diff_base_unavailable", "no_git")


async def test__impact__request_shape(stand: Stand, services: PackCompareService) -> None:
    ws, _ = await folder_with_scenarios(stand)

    bad_base = await post_op(stand, ws, COURSEWORK, "impact", {"base": "tail"})
    too_many = await post_op(stand, ws, COURSEWORK, "impact", {"scenarios": [f"s{i}" for i in range(201)]})
    unknown = await post_op(stand, ws, COURSEWORK, "impact", {"colour": "red"})

    assert (bad_base.status_code, too_many.status_code, unknown.status_code) == (422, 422, 422)


# ── matrix ───────────────────────────────────────────────────────────────────


async def test__matrix__work_tree__strict_model_and_equal_to_a_direct_calculation(
    stand: Stand, services: PackCompareService
) -> None:
    ws, root = await folder_with_scenarios(stand)
    version, _ = _direct(root, COURSEWORK)

    resp = await post_op(stand, ws, COURSEWORK, "matrix")

    got = parse_matrix(resp)
    side = VersionSide(version, tuple(auto_examples(version)))
    direct = matrix_body(matrix_rows(side, _scenarios(root, COURSEWORK), TODAY))
    assert resp.json() == {
        "workspace_id": ws,
        "pack": COURSEWORK[0],
        "template": COURSEWORK[1],
        "version": COURSEWORK[2],
        "state": "work_tree",
        "revision": got.revision,
        **direct,
    }
    assert [r.scenario for r in got.rows] == ["company-supervisor", "no-supervisor", "university-supervisor"]
    assert all(r.status == "passed" for r in got.rows)
    assert all(c.changed is None for r in got.rows for c in r.cells)


async def test__matrix__selected_scenarios_etag_and_unknown_scenario(
    stand: Stand, services: PackCompareService
) -> None:
    ws, _ = await folder_with_scenarios(stand)

    first = await post_op(stand, ws, COURSEWORK, "matrix", {"scenarios": ["no-supervisor"]})
    again = await post_op(
        stand, ws, COURSEWORK, "matrix", {"scenarios": ["no-supervisor"]}, **{"If-None-Match": first.headers["ETag"]}
    )
    everyone = await post_op(stand, ws, COURSEWORK, "matrix")
    ghost = await post_op(stand, ws, COURSEWORK, "matrix", {"scenarios": ["ghost"]})

    assert [r.scenario for r in parse_matrix(first).rows] == ["no-supervisor"]
    assert again.status_code == 304
    assert everyone.headers["ETag"] != first.headers["ETag"]
    assert (ghost.status_code, ghost.json()["code"]) == (404, "scenario_not_found")


async def test__matrix__scenario_edit_moves_the_etag_and_a_broken_file_is_an_error_row(
    stand: Stand, services: PackCompareService
) -> None:
    ws, _ = await folder_with_scenarios(stand)
    before = await post_op(stand, ws, COURSEWORK, "matrix")

    added = await put_scenario(
        stand, ws, COURSEWORK_TEMPLATE, "wrong-input", scenario_body("С несуществующей вводной", {"kind": "nope"})
    )
    after = await post_op(stand, ws, COURSEWORK, "matrix")

    assert added.status_code == 200, added.text
    assert after.headers["ETag"] != before.headers["ETag"]
    rows = {r.scenario: r for r in parse_matrix(after).rows}
    assert rows["wrong-input"].status == "error"
    assert rows["wrong-input"].message
    assert all(c.status == "error" for c in rows["wrong-input"].cells)
    assert rows["no-supervisor"].status == "passed"


async def test__matrix__against_base_in_a_folder__diff_base_unavailable(
    stand: Stand, services: PackCompareService
) -> None:
    ws, _ = await folder_with_scenarios(stand)

    resp = await post_op(stand, ws, COURSEWORK, "matrix", {"against": "base"})
    head = await post_op(stand, ws, COURSEWORK, "matrix", {"state": "head"})

    for answer in (resp, head):
        assert answer.status_code == 409, answer.text
        assert answer.json()["reason"] == "no_git"


async def test__matrix__200_scenarios_one_per_row_within_the_size_limit(
    stand: Stand, services: PackCompareService
) -> None:
    many = {
        f"hse-cs-sse/templates/coursework/scenarios/many-{i:03d}.yaml": (
            f"format: 1\nname:\n  ru: Сценарий {i}\ninputs:\n  supervisor: {('university', 'company', 'none')[i % 3]}\n"
        ).encode()
        for i in range(197)
    }
    ws, _ = await folder_with_scenarios(stand, many)  # 197 новых и 3 стартовых: ровно 200 файлов
    started = time.perf_counter()

    resp = await post_op(stand, ws, COURSEWORK, "matrix")

    elapsed = time.perf_counter() - started
    got = parse_matrix(resp)
    assert len(got.rows) == 200
    assert len(resp.content) < 8 * 1024 * 1024
    assert elapsed < 20, elapsed
    # Все сценарии без ожидания, кроме стартовых, помечены `unchecked`.
    assert sum(1 for r in got.rows if r.status == "unchecked") == 197


# ── права, чтение, пределы ───────────────────────────────────────────────────


async def test__section_turned_off__all_three_are_refused_before_anything_is_read(stand: Stand) -> None:
    ws, _ = await folder_with_scenarios(stand)
    off = await stand.client.put(f"{API}/section", json={"enabled": False})
    assert off.status_code == 200, off.text

    for op, body in (("compare", {"left": {}, "right": {}}), ("impact", {}), ("matrix", {})):
        resp = await post_op(stand, ws, COURSEWORK, op, body)
        assert resp.status_code == 404, op
        assert resp.json()["code"] == "pack_studio_disabled"


async def test__all_three__only_read__the_tree_is_untouched(stand: Stand, services: PackCompareService) -> None:
    ws, root = await folder_with_scenarios(stand)
    before = tree_digest(root)

    await post_op(stand, ws, COURSEWORK, "compare", {"left": {"inputs": _UNIVERSITY}, "right": {"inputs": _COMPANY}})
    await post_op(stand, ws, COURSEWORK, "matrix")
    await post_op(stand, ws, COURSEWORK, "impact")  # 409: папка без git; ничего не пишет и отказ

    assert tree_digest(root) == before
    listing = await stand.client.get(scenarios_url(ws, COURSEWORK_TEMPLATE))
    assert [e["id"] for e in listing.json()["scenarios"]] == [
        "company-supervisor",
        "no-supervisor",
        "university-supervisor",
    ]


async def test__matrix__over_the_time_limit__503_outcome_busy_with_retry_after(
    stand: Stand, services: PackCompareService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, _ = await folder_with_scenarios(stand)
    await post_outcome(stand, ws, COURSEWORK)  # разбор версии не входит в срок расчёта
    monkeypatch.setattr(services, "_limits", replace(services._limits, timeout_s=0.0))

    resp = await post_op(stand, ws, COURSEWORK, "matrix")

    assert resp.status_code == 503, resp.text
    assert (resp.json()["code"], resp.json()["reason"]) == ("outcome_busy", "timeout")
    assert resp.headers["Retry-After"] == str(services._limits.retry_after_s)
    # Неудачный расчёт в кэш не попал: с нормальным пределом тот же запрос проходит.
    monkeypatch.setattr(services, "_limits", CompareLimits())
    assert (await post_op(stand, ws, COURSEWORK, "matrix")).status_code == 200


async def test__matrix__all_slots_taken__overloaded_answers_after_the_wait(
    stand: Stand, services: PackCompareService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, _ = await folder_with_scenarios(stand)
    monkeypatch.setattr(services, "_limits", replace(services._limits, timeout_s=0.2))
    monkeypatch.setattr(services, "_slots", asyncio.Semaphore(0))
    started = time.perf_counter()

    resp = await post_op(stand, ws, COURSEWORK, "matrix")

    assert time.perf_counter() - started < 5
    assert resp.status_code == 503, resp.text
    assert resp.json()["reason"] == "overloaded"
    assert resp.headers["Retry-After"] == str(services._limits.retry_after_s)


async def test__matrix__response_over_the_size_limit__413_outcome_too_large(
    stand: Stand, services: PackCompareService, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws, _ = await folder_with_scenarios(stand)
    monkeypatch.setattr(services, "_limits", replace(services._limits, response_bytes=1000))

    resp = await post_op(stand, ws, COURSEWORK, "matrix")

    assert resp.status_code == 413, resp.text
    body = resp.json()
    assert (body["code"], body["limit"]) == ("outcome_too_large", 1000)
    assert body["size"] > 1000
    # Меньше сценариев: тот же запрос проходит под тем же пределом? Строка весит больше 1000 знаков, поэтому нет.
    one = await post_op(stand, ws, COURSEWORK, "matrix", {"scenarios": ["no-supervisor"]})
    assert one.status_code == 413


async def test__defaults__follow_the_design(services: PackCompareService) -> None:
    limits = services._limits

    assert (limits.timeout_s, limits.concurrency, limits.response_bytes) == (20.0, 2, 8 * 1024 * 1024)
