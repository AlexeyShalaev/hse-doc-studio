"""«Почему?» на выпущенных версиях репозитория: ВКР `hse-cs-se` 2026.1.2 и курсовой проект `hse-cs-sse` 2026.1.6
(template-studio-outcome.md, 4.6, срез O5).

Ядро объяснения (`core/pack_studio/outcome/explain.py`) и соседние комбинации
(`use_cases/pack_studio/outcome/explain.py`) проверяются без HTTP. Главное: цепочка равна `why` результата, а
«что если» совпадает с настоящим пересчётом ядром: для каждого элемента сравниваются все соседние значения всех
вводных, а не выборка."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeExplainRequest, PackOutcomeExplainResponse
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.explain import (
    ABSENT,
    MAX_COUNTERFACTUALS,
    MAX_READERS,
    Neighbor,
    element_infos,
    element_states,
    explain_element,
    find_element,
    inputs_of_entry,
)
from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError, input_specs
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef, Outcome
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.preview import PreviewExample, auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.explain import EXPLAIN_INCLUDE, MAX_NEIGHBORS, neighbors_of
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve

_ROOT = Path(__file__).resolve().parents[7]
_FIXTURES = _ROOT / "contracts" / "pack-studio" / "fixtures"
TODAY = date(2026, 11, 16)

VKR = ("hse-cs-se", "vkr", "2026.1.2")
COURSEWORK = ("hse-cs-sse", "coursework", "2026.1.6")

# Комбинации, на которых сверяется всё: умолчания, NDA с одним руководством, команда без научрука, чужие значения.
_VKR_COMBOS: list[dict[str, str]] = [
    {},
    {"meta.nda": "yes", "meta.manuals": "Только программиста"},
    {"staffing": "team2", "supervisor": "none", "academic_supervisor": "no"},
    {"kind": "research", "co_supervisor": "yes", "answer.ai_declaration.used_ai": "yes"},
]
_COURSEWORK_COMBOS: list[dict[str, str]] = [
    {},
    {"co_supervisor": "yes", "supervisor": "company"},
    {"kind": "research", "academic_supervisor": "no"},
]


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(_ROOT / "packs")


def _load(repo: YamlTemplateRepository, ref: tuple[str, str, str]) -> TemplateVersion:
    found = repo.get_version(*ref)
    assert found is not None
    return found


@pytest.fixture(scope="module")
def vkr(repo: YamlTemplateRepository) -> TemplateVersion:
    return _load(repo, VKR)


@pytest.fixture(scope="module")
def coursework(repo: YamlTemplateRepository) -> TemplateVersion:
    return _load(repo, COURSEWORK)


def _example(version: TemplateVersion) -> PreviewExample:
    return auto_examples(version)[0]


def _outcome(version: TemplateVersion, inputs: dict[str, str]) -> Outcome:
    return resolve(version, inputs, _example(version), TODAY, include=EXPLAIN_INCLUDE)


def _explain(version: TemplateVersion, inputs: dict[str, str], section: str, element_id: str) -> dict[str, Any]:
    outcome = _outcome(version, inputs)
    neighbors = neighbors_of(version, outcome, _example(version), TODAY)
    ref = ElementRef(section, element_id)  # type: ignore[arg-type]
    explanation = explain_element(outcome, ref, neighbors)
    assert explanation is not None, (section, element_id)
    body = to_json(explanation)
    PackOutcomeExplainResponse.model_validate(body)
    return dict(body)


def _counterfactuals(body: dict[str, Any]) -> dict[tuple[str, str], str]:
    return {(c["input"], c["value"]): c["result"] for c in body["counterfactuals"]}


# ── Эталон контракта ─────────────────────────────────────────────────────────


def _fixture(schema: str, name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


def test__golden__operator_manual_fixture_is_reproduced_by_the_resolver(vkr: TemplateVersion) -> None:
    request = _fixture("PackOutcomeExplainRequest", "operator_manual")
    PackOutcomeExplainRequest.model_validate(request)

    got = _explain(vkr, request["inputs"], request["element"]["section"], request["element"]["id"])

    assert got == _fixture("PackOutcomeExplain", "operator_manual")


# ── Цепочка ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("ref", "combos"), [(VKR, _VKR_COMBOS), (COURSEWORK, _COURSEWORK_COMBOS)], ids=["vkr", "coursework"]
)
def test__chain__every_element_is_explained_and_its_chain_is_its_why(
    repo: YamlTemplateRepository, ref: tuple[str, str, str], combos: list[dict[str, str]]
) -> None:
    version = _load(repo, ref)
    for combo in combos:
        outcome = _outcome(version, combo)
        trace = {t.id: t for t in outcome.trace}
        for (section, element_id), info in element_infos(outcome).items():
            body = to_json(explain_element(outcome, ElementRef(section, element_id), ()))  # type: ignore[arg-type]

            PackOutcomeExplainResponse.model_validate({**body, "counterfactuals": []})
            assert [t["id"] for t in body["chain"]] == list(info.why), (combo, section, element_id)
            assert body["chain"] == [to_json(trace[i]) for i in info.why]
            assert body["state"] == info.state
            assert body["element"] == {"section": section, "id": element_id}


def test__chain__document_chain_equals_the_why_of_the_outcome_for_every_document(vkr: TemplateVersion) -> None:
    outcome = _outcome(vkr, {"meta.nda": "no", "meta.manuals": "Только программиста"})

    for doc in outcome.documents:
        body = _explain(vkr, {"meta.nda": "no", "meta.manuals": "Только программиста"}, "documents", doc.id)

        assert [t["id"] for t in body["chain"]] == list(doc.why)
        assert body["state"] == doc.state


def test__chain__included_document__every_rule_held_and_the_state_is_active(vkr: TemplateVersion) -> None:
    body = _explain(vkr, {"meta.manuals": "Только программиста"}, "documents", "programmer_manual")

    assert body["state"] == "active"
    gates = [t for t in body["chain"] if t["effect"] == "gate"]
    assert gates
    assert {t["status"] for t in gates} == {"held"}
    assert {t["rule"]["origin"] for t in body["chain"]} == {"manifest", "builtin"}


def test__chain__excluded_document__the_blocking_rule_is_builtin_and_the_rest_are_in_order(
    vkr: TemplateVersion,
) -> None:
    body = _explain(vkr, {"meta.manuals": "Только программиста"}, "documents", "operator_manual")

    assert body["state"] == "inactive"
    assert [(t["kind"], t["status"]) for t in body["chain"]] == [
        ("supported_kinds", "held"),
        ("supported_staffing", "held"),
        ("builtin_gate", "not_held"),
        ("supported_langs", "held"),
    ]
    blocking = next(t for t in body["chain"] if t["status"] == "not_held")
    assert blocking["rule"] == {"origin": "builtin", "file": None, "pointer": None, "builtin": "manuals_gate"}
    assert blocking["terms"] == [{"op": "contains_any", "subject": "meta.manuals", "expected": ["оператора"]}]
    assert blocking["actual"] == {"meta.manuals": "Только программиста"}


def test__chain__skipped_rule_stays_in_the_chain_as_skipped(vkr: TemplateVersion) -> None:
    body = _explain(vkr, {"kind": "research"}, "documents", "operator_manual")

    assert body["state"] == "absent"
    statuses = {t["kind"]: t["status"] for t in body["chain"]}
    assert statuses["supported_kinds"] == "not_held"
    assert statuses["supported_staffing"] == "skipped"
    assert statuses["builtin_gate"] == "skipped"


def test__chain__rules_know_their_place_in_the_manifest(vkr: TemplateVersion) -> None:
    body = _explain(vkr, {}, "documents", "operator_manual")

    manifest = [t["rule"] for t in body["chain"] if t["rule"]["origin"] == "manifest"]
    assert manifest
    assert {r["file"] for r in manifest} == {"files/operator_manual/doc.yaml"}
    assert all(r["pointer"].startswith("/") for r in manifest)


def test__chain__nda_item_of_a_point__off_with_the_document_reasons_and_on_with_an_empty_chain(
    vkr: TemplateVersion,
) -> None:
    off = _explain(vkr, {"meta.nda": "no"}, "points", "final/nda")
    on = _explain(vkr, {"meta.nda": "yes"}, "points", "final/nda")

    assert off["state"] == ABSENT
    assert "nda_gate" in {t["rule"]["builtin"] for t in off["chain"]}
    blocking = next(t for t in off["chain"] if t["status"] == "not_held")
    assert blocking["actual"] == {"meta.nda": "no"}
    assert on["state"] == "present"
    assert on["chain"] == []
    assert _counterfactuals(off) == {("meta.nda", "yes"): "present"}
    assert _counterfactuals(on) == {("meta.nda", "no"): "absent"}


def test__chain__nda_document_itself__gate_follows_the_nda_input(vkr: TemplateVersion) -> None:
    off = _explain(vkr, {"meta.nda": "no"}, "documents", "nda")
    on = _explain(vkr, {"meta.nda": "yes"}, "documents", "nda")

    assert (off["state"], on["state"]) == ("inactive", "active")
    assert ("meta.nda", "yes") in _counterfactuals(off)
    assert ("meta.nda", "no") in _counterfactuals(on)


def test__chain__route_slot_with_a_condition__follows_the_person(coursework: TemplateVersion) -> None:
    pair = "topic-approval/topic_application/co_supervisor"

    on = _explain(coursework, {"co_supervisor": "yes"}, "route", pair)
    off = _explain(coursework, {"co_supervisor": "no"}, "route", pair)

    assert on["state"] == "present"
    (held,) = on["chain"]
    assert (held["kind"], held["status"], held["effect"]) == ("slot_when", "held", "add")
    assert held["rule"]["pointer"].endswith("/when")
    assert held["rule"]["file"] == "version.yaml"
    assert off["state"] == ABSENT
    (not_held,) = off["chain"]
    assert not_held["status"] == "not_held"
    assert _counterfactuals(off)[("co_supervisor", "yes")] == "present"
    assert _counterfactuals(on)[("co_supervisor", "no")] == "absent"


def test__chain__route_step_collects_the_order_and_the_slots_of_its_people(coursework: TemplateVersion) -> None:
    outcome = _outcome(coursework, {"co_supervisor": "yes"})
    steps = [
        (point.id, number)
        for point in outcome.points
        for number, _ in enumerate(point.route.steps, start=1)
        if point.id == "topic-approval"
    ]
    assert steps

    for point_id, number in steps:
        body = _explain(coursework, {"co_supervisor": "yes"}, "route", f"{point_id}/step/{number}")

        assert body["state"] == "present"
        assert body["chain"], (point_id, number)
        assert body["chain"][0]["kind"] == "route_order"


def test__chain__whole_route_of_a_point_is_explained_by_its_order(vkr: TemplateVersion) -> None:
    body = _explain(vkr, {}, "route", "final")

    assert [t["kind"] for t in body["chain"]] == ["route_order"]


def test__chain__field_and_form_field(vkr: TemplateVersion) -> None:
    form_field = _explain(vkr, {"answer.ai_declaration.used_ai": "no"}, "forms", "ai_declaration/tools")
    shown = _explain(vkr, {"answer.ai_declaration.used_ai": "yes"}, "forms", "ai_declaration/tools")
    meta = _explain(vkr, {"kind": "project"}, "meta", "nda")

    assert (form_field["state"], shown["state"]) == (ABSENT, "present")
    (rule,) = form_field["chain"]
    assert (rule["kind"], rule["status"], rule["effect"]) == ("visible_if", "not_held", "display")
    assert rule["terms"] == [{"op": "equals", "subject": "answer.ai_declaration.used_ai", "expected": ["yes"]}]
    assert _counterfactuals(form_field) == {("answer.ai_declaration.used_ai", "yes"): "present"}
    assert meta["state"] == "present"


def test__chain__participant_without_a_person__no_rules_but_the_input_that_adds_one(vkr: TemplateVersion) -> None:
    absent = _explain(vkr, {"co_supervisor": "no"}, "participants", "co_supervisor")
    present = _explain(vkr, {"co_supervisor": "yes"}, "participants", "co_supervisor")

    assert (absent["state"], present["state"]) == (ABSENT, "present")
    assert absent["chain"] == []
    assert _counterfactuals(absent) == {("co_supervisor", "yes"): "present"}
    assert _counterfactuals(present) == {("co_supervisor", "no"): "absent"}


def test__chain__check_rule_is_explained_and_its_state_is_enabled(coursework: TemplateVersion) -> None:
    outcome = _outcome(coursework, {})
    assert outcome.checks

    for rule in outcome.checks:
        body = _explain(coursework, {}, "checks", rule.id)

        assert body["state"] == ("present" if rule.enabled else ABSENT)


# ── Соседи по правилам ───────────────────────────────────────────────────────


def test__readers__are_the_other_subjects_of_the_chain_decisions(vkr: TemplateVersion) -> None:
    outcome = _outcome(vkr, {})
    shared = [t for t in outcome.trace if len(t.subjects) > 1]
    assert shared, "в ВКР есть решения, которые касаются нескольких элементов"
    entry = shared[0]
    subject = entry.subjects[0]

    body = _explain(vkr, {}, subject.section, subject.id)

    readers = [(r["section"], r["id"]) for r in body["readers"]]
    assert {(s.section, s.id) for s in entry.subjects if s != subject} <= set(readers)
    assert (subject.section, subject.id) not in readers
    assert len(readers) == len(set(readers))


def test__readers__each_reader_shares_a_decision_with_the_element(vkr: TemplateVersion) -> None:
    outcome = _outcome(vkr, {})
    for (section, element_id), info in element_infos(outcome).items():
        body = to_json(explain_element(outcome, ElementRef(section, element_id), ()))  # type: ignore[arg-type]
        reader_keys = {(r["section"], r["id"]) for r in body["readers"]}
        expected = {
            (s.section, s.id)
            for entry in outcome.trace
            if entry.id in info.why
            for s in entry.subjects
            if (s.section, s.id) != (section, element_id)
        }

        assert reader_keys == expected, (section, element_id)


def test__readers__are_capped(vkr: TemplateVersion) -> None:
    assert MAX_READERS == 64


# ── «Что если» ───────────────────────────────────────────────────────────────


def _oracle(version: TemplateVersion, inputs: dict[str, str]) -> tuple[Outcome, list[tuple[str, str, dict]]]:
    """Настоящий пересчёт: каждая вводная в каждое своё другое значение, без помощи кода объяснения."""
    base = _outcome(version, inputs)
    found: list[tuple[str, str, dict]] = []
    for spec in input_specs(version):
        for value in spec.values:
            if value == base.inputs[spec.id]:
                continue
            other = resolve(version, {**base.inputs, spec.id: value}, _example(version), TODAY, include=EXPLAIN_INCLUDE)
            found.append((spec.id, value, element_states(other)))
    return base, found


@pytest.mark.parametrize(
    ("ref", "combos"), [(VKR, _VKR_COMBOS), (COURSEWORK, _COURSEWORK_COMBOS)], ids=["vkr", "coursework"]
)
def test__what_if__equals_the_real_recalculation_for_every_element(
    repo: YamlTemplateRepository, ref: tuple[str, str, str], combos: list[dict[str, str]]
) -> None:
    version = _load(repo, ref)
    checked = flipping = 0
    for combo in combos:
        base, oracle = _oracle(version, combo)
        neighbors = neighbors_of(version, base, _example(version), TODAY)
        for (section, element_id), info in element_infos(base).items():
            expected = {
                (name, value): states.get((section, element_id), ABSENT)
                for name, value, states in oracle
                if states.get((section, element_id), ABSENT) != info.state
            }
            explanation = explain_element(base, ElementRef(section, element_id), neighbors)  # type: ignore[arg-type]
            assert explanation is not None
            got = {(c.input, c.value): c.result for c in explanation.counterfactuals}

            assert len(expected) <= MAX_COUNTERFACTUALS, (combo, section, element_id)
            assert got == expected, (combo, section, element_id)
            checked += 1
            flipping += bool(expected)

    assert checked > 100
    assert flipping > 10


def test__what_if__every_proposed_value_really_changes_the_element(vkr: TemplateVersion) -> None:
    inputs = {"meta.manuals": "Только программиста"}
    body = _explain(vkr, inputs, "documents", "operator_manual")

    assert body["counterfactuals"]
    for change in body["counterfactuals"]:
        after = resolve(vkr, {**inputs, change["input"]: change["value"]}, _example(vkr), TODAY)
        doc = next(d for d in after.documents if d.id == "operator_manual")
        assert doc.state == change["result"]
        assert doc.state != body["state"]


def test__what_if__inputs_of_blocking_rules_come_first(vkr: TemplateVersion) -> None:
    body = _explain(vkr, {"meta.manuals": "Только программиста"}, "documents", "operator_manual")

    assert [c["input"] for c in body["counterfactuals"]] == ["meta.manuals", "meta.manuals", "kind"]


def test__what_if__an_element_nothing_changes_has_none(vkr: TemplateVersion) -> None:
    body = _explain(vkr, {}, "documents", "thesis")

    assert body["state"] == "active"
    assert body["counterfactuals"] == []


def test__what_if__the_input_itself_is_never_proposed_at_its_current_value(vkr: TemplateVersion) -> None:
    inputs = {"meta.manuals": "Только программиста", "kind": "project"}
    body = _explain(vkr, inputs, "documents", "operator_manual")

    for change in body["counterfactuals"]:
        assert change["value"] != _outcome(vkr, inputs).inputs[change["input"]]


def test__what_if__result_list_is_capped_in_the_contract_limit(vkr: TemplateVersion) -> None:
    outcome = _outcome(vkr, {})
    key = ("documents", "thesis")
    flipped = [Neighbor(f"input{i}", "x", {key: "inactive"}) for i in range(MAX_COUNTERFACTUALS * 3)]

    explanation = explain_element(outcome, ElementRef("documents", "thesis"), flipped)

    assert explanation is not None
    assert len(explanation.counterfactuals) == MAX_COUNTERFACTUALS
    assert MAX_COUNTERFACTUALS <= 32  # предел модели контракта


# ── Соседние комбинации ──────────────────────────────────────────────────────


def test__neighbors__one_per_other_value_of_every_input(vkr: TemplateVersion) -> None:
    base = _outcome(vkr, {})
    expected = sum(len(spec.values) - 1 for spec in input_specs(vkr))

    neighbors = neighbors_of(vkr, base, _example(vkr), TODAY)

    assert len(neighbors) == expected == 14
    assert all(n.value != base.inputs[n.input] for n in neighbors)


def test__neighbors__are_limited_and_the_inputs_read_by_decisions_come_first(vkr: TemplateVersion) -> None:
    base = _outcome(vkr, {})

    neighbors = neighbors_of(vkr, base, _example(vkr), TODAY, limit=3)

    assert len(neighbors) == 3
    assert MAX_NEIGHBORS >= 14
    read = {name for entry in base.trace for name in inputs_of_entry(entry, set(base.inputs))}
    assert {n.input for n in neighbors} <= read


def test__neighbors__a_combination_the_core_refuses_is_skipped(vkr: TemplateVersion) -> None:
    base = _outcome(vkr, {})
    calls: list[dict[str, str]] = []

    def refusing(version: TemplateVersion, inputs: dict[str, str], *args: Any, **kwargs: Any) -> Outcome:
        calls.append(inputs)
        if inputs["kind"] != base.inputs["kind"]:
            raise OutcomeInputError("kind", inputs["kind"], "refused")
        return resolve(version, inputs, *args, **kwargs)

    neighbors = neighbors_of(vkr, base, _example(vkr), TODAY, resolver=refusing)

    assert len(calls) == 14
    assert len(neighbors) == 13
    assert "kind" not in {n.input for n in neighbors}


def test__neighbors__are_computed_without_the_trace(vkr: TemplateVersion) -> None:
    base = _outcome(vkr, {})
    seen: list[bool] = []

    def spy(version: TemplateVersion, inputs: dict[str, str], *args: Any, **kwargs: Any) -> Outcome:
        seen.append(kwargs["trace"])
        return resolve(version, inputs, *args, **kwargs)

    neighbors_of(vkr, base, _example(vkr), TODAY, resolver=spy)

    assert seen
    assert not any(seen)


# ── Неизвестный элемент ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("section", "element_id"),
    [
        ("documents", "no_such_document"),
        ("points", "final/no_such_item"),
        ("route", "final/thesis/no_such_slot"),
        ("route", "final/step/99"),
        ("forms", "ai_declaration/no_such_field"),
        ("participants", "nobody"),
        ("meta", ""),
    ],
)
def test__unknown_element__is_not_found(vkr: TemplateVersion, section: str, element_id: str) -> None:
    outcome = _outcome(vkr, {})
    ref = ElementRef(section, element_id)  # type: ignore[arg-type]

    assert find_element(outcome, ref) is None
    assert explain_element(outcome, ref, ()) is None


def test__unknown_element__a_section_the_outcome_lacks_is_not_found_without_checks(vkr: TemplateVersion) -> None:
    outcome = resolve(vkr, {}, _example(vkr), TODAY)

    assert find_element(outcome, ElementRef("checks", "any")) is None
