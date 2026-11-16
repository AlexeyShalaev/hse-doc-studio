"""Внутренняя согласованность эталонов вычислителя результата (`docs/design/template-studio-outcome.md`, раздел 4).

Сверка формы эталонов с моделями делает `test_pack_studio_contract.py`. Здесь то, что схема выразить не может: ссылки
`why` указывают на существующие решения `trace`, а решения помнят свои элементы; сводки сходятся с телом; таблица атласа
согласована с измерениями. Эталоны собраны существующим кодом расчёта на реальных паках, поэтому эти связи держатся
сами, и нарушение значит, что эталон правили руками или контракт разошёлся.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas import pack_studio_outcome as out
from pydantic import ValidationError

_FIXTURES = Path(__file__).resolve().parents[5] / "contracts" / "pack-studio" / "fixtures"
_SECTIONS = ["documents", "meta", "forms", "participants", "points", "route", "checks"]


def _load(schema: str, name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


def _outcomes() -> list[tuple[str, dict[str, Any]]]:
    return [
        (p.stem, json.loads(p.read_text(encoding="utf-8"))) for p in sorted((_FIXTURES / "PackOutcome").glob("*.json"))
    ]


def _why_lists(node: Any) -> list[list[str]]:
    found: list[list[str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "why":
                found.append(value)
            elif key != "trace":
                found.extend(_why_lists(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_why_lists(item))
    return found


@pytest.mark.parametrize(("name", "body"), _outcomes(), ids=[n for n, _ in _outcomes()])
def test__outcome__trace_ids_are_unique_and_every_why_points_at_a_decision(name: str, body: dict[str, Any]) -> None:
    ids = [t["id"] for t in body["trace"]]

    assert len(ids) == len(set(ids))
    referenced = {i for why in _why_lists(body) for i in why}
    assert referenced <= set(ids)
    # Решение без единого элемента никому не нужно: трасса не копит мусор.
    assert {t["id"] for t in body["trace"] if not t["subjects"]} == set()


@pytest.mark.parametrize(("name", "body"), _outcomes(), ids=[n for n, _ in _outcomes()])
def test__outcome__decisions_remember_the_elements_they_explain(name: str, body: dict[str, Any]) -> None:
    subjects = {t["id"]: {(s["section"], s["id"]) for s in t["subjects"]} for t in body["trace"]}
    expected: list[tuple[tuple[str, str], list[str]]] = []
    expected += [(("documents", d["id"]), d["why"]) for d in body["documents"]]
    expected += [(("meta", f["id"]), f["why"]) for f in body["meta"]]
    for form in body["forms"]:
        expected.append((("forms", form["id"]), form["why"]))
        expected += [(("forms", f"{form['id']}/{f['id']}"), f["why"]) for f in form["fields"]]
    for point in body["points"]:
        expected += [(("points", f"{point['id']}/{i['doc_id']}"), i["why"]) for i in point["items"] if i["why"]]
        expected.append((("route", point["id"]), point["route"]["why"]))

    broken = [(element, i) for element, why in expected for i in why if element not in subjects[i]]

    # `why` предмета документа пункта может ссылаться на решение самого документа: оно помнит документ, не пункт.
    allowed = {
        (element, i)
        for element, i in broken
        if element[0] == "points" and any(e[0] == "documents" for e in subjects[i])
    }
    assert set(broken) <= allowed


@pytest.mark.parametrize(("name", "body"), _outcomes(), ids=[n for n, _ in _outcomes()])
def test__outcome__digest_agrees_with_the_body(name: str, body: dict[str, Any]) -> None:
    digest = body["digest"]

    assert digest["documents"] == {d["id"]: d["state"] for d in body["documents"]}
    assert digest["participants"] == [p["persona"] for p in body["participants"] if p["present"]]
    assert digest["meta_visible"] == [f["id"] for f in body["meta"] if f["visible"]]
    assert [p["id"] for p in digest["points"]] == [p["id"] for p in body["points"]]
    for point, summary in zip(body["points"], digest["points"], strict=True):
        assert summary["items"] == [i["doc_id"] for i in point["items"] if i["active"]]
        assert summary["steps"] == [[person["persona"] for person in step] for step in point["route"]["steps"]]
        assert summary["pairs"] == len(point["route"]["pairs"])
    assert [s["section"] for s in digest["sections"]] == _SECTIONS


@pytest.mark.parametrize(("name", "body"), _outcomes(), ids=[n for n, _ in _outcomes()])
def test__outcome__documents_keep_the_state_rules(name: str, body: dict[str, Any]) -> None:
    for doc in body["documents"]:
        assert (doc["state"] == "absent") == (not doc["instances"])
        assert (doc["state"] == "absent") == (doc["source_file"] is None)
        chosen = [v for v in doc["variants"] if v["chosen"]]
        assert len(chosen) <= 1
        assert all(v["available"] for v in chosen)
    for point in body["points"]:
        for item in point["items"]:
            assert (item["off_reason"] is None) == item["active"]


def test__outcome__only_requested_heavy_parts_are_present() -> None:
    plain = _load("PackOutcome", "vkr_nda_programmer_only")
    heavy = _load("PackOutcome", "coursework_company_cosupervisor")
    request = _load("PackOutcomeRequest", "company_cosupervisor")

    assert plain["checks"] is None
    assert plain["branches"] is None
    assert heavy["checks"]
    assert heavy["branches"]
    assert set(request["include"]) == {"checks", "branches"}


def test__branches__current_value_has_no_delta_and_the_rest_have_one() -> None:
    heavy = _load("PackOutcome", "coursework_company_cosupervisor")

    for branch in heavy["branches"]:
        chosen = [a for a in branch["alternatives"] if a["value"] == branch["chosen"]]
        assert len(chosen) == 1
        assert chosen[0]["delta"] == []
        assert chosen[0]["fingerprint"] == heavy["fingerprint"]
        assert branch["input"] in heavy["inputs"]


def test__atlas__table_agrees_with_dimensions_and_outcomes() -> None:
    atlas = _load("PackOutcomeAtlas", "coursework")
    dims = atlas["dimensions"]
    outcome_ids = {o["id"] for o in atlas["outcomes"]}

    assert atlas["rows_total"] == len(atlas["rows"])
    assert atlas["outcomes_distinct"] == len(atlas["outcomes"])
    assert {r["outcome"] for r in atlas["rows"]} == outcome_ids
    assert len({r["key"] for r in atlas["rows"]}) == len(atlas["rows"])
    assert all(len(r["key"].split("|")) == len(dims) for r in atlas["rows"])
    full = 1
    for dim in dims:
        full *= len(dim["values"])
    assert atlas["rows_total"] == full
    assert atlas["rows_total"] <= atlas["combinations_total"]
    per_outcome = Counter(r["outcome"] for r in atlas["rows"])
    assert {o["id"]: o["rows"] for o in atlas["outcomes"]} == dict(per_outcome)
    assert all(dim["default"] in dim["values"] and dim["affects"] for dim in dims)
    ignored = {i["input"] for i in atlas["ignored"]}
    assert ignored.isdisjoint({d["input"] for d in dims})


def test__atlas__every_row_value_is_a_value_of_its_dimension() -> None:
    atlas = _load("PackOutcomeAtlas", "coursework")
    dims = atlas["dimensions"]

    for row in atlas["rows"]:
        for value, dim in zip(row["key"].split("|"), dims, strict=True):
            assert value in dim["values"]


def test__inputs__defaults_are_values_and_every_input_has_a_group() -> None:
    body = _load("PackOutcomeInputs", "vkr")

    assert set(body["defaults"]) == {i["id"] for i in body["inputs"]}
    for item in body["inputs"]:
        assert body["defaults"][item["id"]] == item["default"]
        assert item["default"] in {v["value"] for v in item["values"]}
    assert {i["group"] for i in body["inputs"]} >= {"project", "people", "meta", "answers"}
    assert any(e["id"] == body["default_example"] for e in body["examples"])


def _count_changes(changes: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for change in changes:
        row = result.setdefault(change["section"], {"added": 0, "changed": 0, "removed": 0})
        row[{"+": "added", "~": "changed", "-": "removed"}[change["symbol"]]] += 1
    return result


def _summary(entries: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {e["section"]: {k: e[k] for k in ("added", "changed", "removed")} for e in entries}


def test__compare__summary_is_the_count_of_changes() -> None:
    body = _load("PackOutcomeCompare", "two_scenarios")

    assert _summary(body["summary"]) == _count_changes(body["changes"])
    assert body["identical"] is (not body["changes"])
    assert (body["left"]["fingerprint"] == body["right"]["fingerprint"]) is body["identical"]
    assert {c["symbol"] for c in body["changes"]} <= {"+", "~", "-"}


def test__impact__summary_agrees_with_scenarios() -> None:
    body = _load("PackOutcomeImpact", "coursework")
    summary = body["summary"]
    counts = Counter(s["status"] for s in body["scenarios"])

    assert summary["scenarios_total"] == len(body["scenarios"])
    assert summary["scenarios_changed"] == counts["changed"]
    assert summary["scenarios_unchanged"] == counts["unchanged"]
    assert summary["scenarios_error"] == counts["error"]
    assert _summary(summary["sections"]) == _count_changes([c for s in body["scenarios"] for c in s["changes"]])
    assert all(bool(s["changes"]) == (s["status"] == "changed") for s in body["scenarios"])
    assert summary["atlas"]["rows_changed"] <= summary["atlas"]["rows_total"]
    assert body["base_revision"] != body["work_tree_revision"]


def test__run__counts_and_coverage_agree_with_results() -> None:
    body = _load("PackScenarioRun", "coursework_after_edit")
    counts = Counter(r["status"] for r in body["results"])
    cov = body["coverage"]

    assert (body["passed"], body["failed"], body["errors"], body["unchecked"]) == (
        counts["passed"],
        counts["failed"],
        counts["error"],
        counts["unchecked"],
    )
    assert cov["rules_total"] == cov["rules_covered"] + cov["rules_half"] + cov["rules_uncovered"]
    assert len(cov["rules"]) == cov["rules_half"] + cov["rules_uncovered"]
    assert all(bool(r["failures"]) == (r["status"] == "failed") for r in body["results"])


def test__lint__counts_agree_with_findings() -> None:
    body = _load("PackOutcomeLint", "vkr")
    severities = Counter(f["severity"] for f in body["findings"])

    assert body["errors"] == severities["error"]
    assert body["warnings"] == severities["warning"]
    assert {f["rule_id"] for f in body["findings"]} >= {"slot-never-routed", "translation-missing"}


def test__matrix__every_row_has_one_cell_per_column() -> None:
    body = _load("PackOutcomeMatrix", "coursework")

    assert body["columns"] == _SECTIONS
    assert all([c["section"] for c in row["cells"]] == body["columns"] for row in body["rows"])


def test__matrix__cell_status_follows_the_row_and_the_base_comparison() -> None:
    body = _load("PackOutcomeMatrix", "coursework")

    for row in body["rows"]:
        if row["status"] == "error":
            assert row["message"] is not None
            assert all(c["status"] == "error" and c["count"] == 0 for c in row["cells"])
        else:
            assert row["message"] is None
            assert all(c["status"] != "error" for c in row["cells"])
        # Раздел, изменённый против базы, это `changed`; сценарий с таким разделом не может быть `passed`.
        assert all(c["status"] == "changed" for c in row["cells"] if c["changed"])
        if any(c["changed"] for c in row["cells"]):
            assert row["status"] != "unchecked"


def test__compare__reasons_name_a_rule_and_at_least_one_side() -> None:
    body = _load("PackOutcomeCompare", "two_scenarios")
    reasons = [r for c in body["changes"] for r in c["why"]]

    assert reasons
    assert all(r["before"] is not None or r["after"] is not None for r in reasons)
    assert all(r["rule"]["origin"] in {"manifest", "builtin"} for r in reasons)
    assert all(len(c["why"]) <= 6 for c in body["changes"])  # noqa: PLR2004


def test__scenario_list__broken_files_stay_visible_without_content() -> None:
    body = _load("PackScenarioList", "coursework")

    assert len({e["id"] for e in body["scenarios"]}) == len(body["scenarios"])
    for entry in body["scenarios"]:
        assert entry["path"] == f"{body['dir']}/{entry['id']}.yaml"
        assert (entry["scenario"] is None) == (entry["error"] is not None)


def test__scenario__snapshot_is_a_digest_of_the_same_shape() -> None:
    scenario = _load("PackScenario", "coursework_company")

    assert [s["section"] for s in scenario["snapshot"]["sections"]] == _SECTIONS
    assert scenario["format"] == 1


def test__explain__chain_is_made_of_decisions_that_name_the_element() -> None:
    body = _load("PackOutcomeExplain", "operator_manual")
    element = (body["element"]["section"], body["element"]["id"])

    assert body["chain"]
    assert all(element in {(s["section"], s["id"]) for s in t["subjects"]} for t in body["chain"])
    assert {c["result"] for c in body["counterfactuals"]} <= {"active", "inactive", "absent"}


def test__rule_ref__manifest_needs_a_place_and_builtin_needs_a_name() -> None:
    with pytest.raises(ValidationError):
        out.OutcomeRuleRef(origin="manifest", file="version.yaml", pointer=None, builtin=None)
    with pytest.raises(ValidationError):
        out.OutcomeRuleRef(origin="builtin", file=None, pointer=None, builtin=None)

    assert out.OutcomeRuleRef(origin="builtin", file=None, pointer=None, builtin="nda_gate").origin == "builtin"


def test__models__reject_unknown_fields_and_unknown_assertion_kinds() -> None:
    with pytest.raises(ValidationError):
        out.PackOutcomeRequest.model_validate({"state": "head", "colour": "red"})
    with pytest.raises(ValidationError):
        out.PackScenario.model_validate(
            {
                "format": 1,
                "name": {"ru": "x"},
                "inputs": {},
                "assertions": [{"kind": "item_state", "point": "final"}],
            }
        )
    with pytest.raises(ValidationError):
        out.PackOutcomeRequest.model_validate({"state": "yesterday"})


def test__explain__reference_chain_is_the_why_of_the_element_in_the_outcome_reference() -> None:
    request = _load("PackOutcomeExplainRequest", "operator_manual")
    explain = _load("PackOutcomeExplain", "operator_manual")
    outcome = _load("PackOutcome", "vkr_nda_programmer_only")
    trace = {t["id"]: t for t in outcome["trace"]}
    element = request["element"]
    doc = next(d for d in outcome["documents"] if d["id"] == element["id"])

    assert explain["element"] == element
    assert {k: outcome["inputs"][k] for k in request["inputs"]} == request["inputs"]
    assert explain["state"] == doc["state"]
    assert [t["id"] for t in explain["chain"]] == doc["why"]
    assert explain["chain"] == [trace[i] for i in doc["why"]]
    # Соседи говорят про другие элементы, а ответ «что если» меняет состояние элемента.
    assert element not in explain["readers"]
    assert all(c["result"] != explain["state"] for c in explain["counterfactuals"])
    assert all(c["input"] in outcome["inputs"] for c in explain["counterfactuals"])


def test__explain__reference_models_are_strict() -> None:
    explain = _load("PackOutcomeExplain", "operator_manual")

    out.PackOutcomeExplainResponse.model_validate(explain)
    with pytest.raises(ValidationError):
        out.PackOutcomeExplainResponse.model_validate({**explain, "extra": 1})
    with pytest.raises(ValidationError):
        out.PackOutcomeExplainResponse.model_validate({k: v for k, v in explain.items() if k != "readers"})
    with pytest.raises(ValidationError):
        out.PackOutcomeExplainResponse.model_validate({**explain, "counterfactuals": [{"input": "kind"}]})
    with pytest.raises(ValidationError):
        out.PackOutcomeExplainRequest.model_validate({"element": {"section": "nope", "id": "x"}})
