"""Вычислитель результата на выпущенных версиях репозитория: ВКР `hse-cs-se` 2026.1.2 и курсовой проект `hse-cs-sse`
2026.1.6.

Паритет с движком держит расхождение под замком: на каждой комбинации переключателей предпросмотра набор активных
документов равен `is_doc_active` и `_build_documents`, пункты равны `_items_off`, маршруты равны `profile_route`.
Эталоны `contracts/pack-studio/fixtures/PackOutcome` сверяются целиком, кроме хэшей (алгоритм отпечатка определяет
`summary.py`, значения в эталонах от прототипа) и полей границы запроса."""

from __future__ import annotations

import itertools
import json
import re
import statistics
import time
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeInputsResponse, PackOutcomeResponse
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.inputs import input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.model import Outcome
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.outcome.predicates import document_in_scope
from hse_doc_studio.core.pack_studio.preview import (
    PreviewExample,
    auto_examples,
    resolve_combination,
    switches_for,
    synthetic_project,
)
from hse_doc_studio.core.pack_studio.submission import ProfileRoute
from hse_doc_studio.core.team import is_doc_active
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.dictionary import inputs_dictionary
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.submission import profile_route, synthetic_core_project

from tests.unit.use_cases.pack_studio.outcome.invariants import assert_contract, assert_links

_ROOT = Path(__file__).resolve().parents[7]
_PACKS = _ROOT / "packs"
_FIXTURES = _ROOT / "contracts" / "pack-studio" / "fixtures"
TODAY = date(2026, 11, 16)

VKR = ("hse-cs-se", "vkr", "2026.1.2")
COURSEWORK = ("hse-cs-sse", "coursework", "2026.1.6")


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(_PACKS)


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


def _combos(version: TemplateVersion) -> Iterator[dict[str, str]]:
    """Все комбинации переключателей предпросмотра (без ответов анкет и вариантов: они структуры не меняют)."""
    switches = switches_for(version, max_meta=None)
    for values in itertools.product(*(s.values for s in switches)):
        yield {s.id: v for s, v in zip(switches, values, strict=True)}


# ── Паритет с движком на всех комбинациях ────────────────────────────────────


def _engine_states(version: TemplateVersion, combo: Mapping[str, str]) -> tuple[dict[str, str], Any, Any]:
    synthetic = synthetic_project(
        version, _example(version), resolve_combination(switches_for(version, max_meta=None), combo), TODAY
    )
    project = synthetic_core_project(version.pack_id, version.template_id, version, synthetic)
    states: dict[str, str] = {}
    for doc_def in version.documents:
        instances = [d for d in project.documents if d.def_id == doc_def.id]
        if not instances:
            states[doc_def.id] = "absent"
        else:
            states[doc_def.id] = "active" if any(is_doc_active(project, d) for d in instances) else "inactive"
        # Предикат предпросмотра и экземпляры движка говорят одно и то же.
        assert document_in_scope(
            doc_def.supported_kinds, doc_def.supported_staffing, str(synthetic.kind), str(synthetic.staffing)
        ) is bool(instances)
    return states, project, synthetic


def _route_key(route: ProfileRoute, persona_of: Mapping[str, str]) -> dict[str, Any]:
    return {
        "steps": [[persona_of.get(p.persona, p.persona) for p in step] for step in route.steps],
        "names": [[p.name for p in step] for step in route.steps],
        "pairs": [
            (
                p.doc_id,
                p.slot_id,
                persona_of.get(p.persona, p.persona),
                p.source.value,
                p.optional,
                p.when and (p.when.person, p.when.role),
            )
            for p in route.pairs
        ],
        "skipped": [(s.doc_id, s.slot_id, s.when and (s.when.person, s.when.role)) for s in route.skipped],
        "may_add": list(route.may_add),
        "order_source": route.order_source,
        "preset": route.preset,
    }


def _outcome_route_key(point: Any) -> dict[str, Any]:
    route = point.route
    return {
        "steps": [[p.persona for p in step] for step in route.steps],
        "names": [[p.name for p in step] for step in route.steps],
        "pairs": [
            (p.doc_id, p.slot_id, p.persona, p.source, p.optional, p.when and (p.when.person, p.when.role))
            for p in route.pairs
        ],
        "skipped": [(s.doc_id, s.slot_id, s.when and (s.when.person, s.when.role)) for s in route.skipped],
        "may_add": [(m.doc_id, m.slot_id) for m in route.may_add],
        "order_source": route.order_source,
        "preset": route.preset,
    }


@pytest.mark.parametrize("ref", [VKR, COURSEWORK], ids=["vkr", "coursework"])
def test__parity__every_combination__documents_items_and_routes_equal_the_engine(
    repo: YamlTemplateRepository, ref: tuple[str, str, str]
) -> None:
    version = _load(repo, ref)
    example = _example(version)
    checked = 0
    for combo in _combos(version):
        outcome = resolve(version, combo, example, TODAY, trace=False)
        states, project, synthetic = _engine_states(version, combo)

        assert {d.id: d.state for d in outcome.documents} == states, combo
        persona_of = (
            {a.slug: f"author{i}" for i, a in enumerate(synthetic.authors, start=1)}
            if len(synthetic.authors) > 1
            else {}
        )
        for point, profile in zip(outcome.points, version.pack_submission.profiles, strict=True):
            engine = profile_route(project, version, profile)
            assert _outcome_route_key(point) == _route_key(engine, persona_of), (combo, profile.id)
            assert {i.doc_id for i in point.items if not i.active} == set(engine.items_off), (combo, profile.id)
        checked += 1

    assert checked > 0


def test__parity__combination_counts_match_the_design_prototype(vkr: TemplateVersion) -> None:
    assert sum(1 for _ in _combos(vkr)) == 864


def test__parity__whole_scale_of_the_vkr_is_the_documented_number_of_decisions(vkr: TemplateVersion) -> None:
    outcome = resolve(vkr, {"meta.nda": "yes", "meta.manuals": "Только программиста"}, _example(vkr), TODAY)

    assert len(outcome.trace) == 68


# ── Контракт на реальных версиях ─────────────────────────────────────────────


def _sample(version: TemplateVersion, step: int) -> list[dict[str, str]]:
    return list(itertools.islice(_combos(version), 0, None, step))


@pytest.mark.parametrize("ref", [VKR, COURSEWORK], ids=["vkr", "coursework"])
def test__contract__sampled_combinations_are_accepted_by_the_strict_models(
    repo: YamlTemplateRepository, ref: tuple[str, str, str]
) -> None:
    version = _load(repo, ref)
    for combo in _sample(version, 37):
        assert_contract(resolve(version, combo, _example(version), TODAY, include={"checks", "branches"}))


def test__contract__answers_and_variants_are_inputs_and_change_only_what_they_should(vkr: TemplateVersion) -> None:
    base = resolve(vkr, {}, _example(vkr), TODAY)
    ai = resolve(vkr, {"answer.ai_declaration.used_ai": "yes"}, _example(vkr), TODAY)
    reveal = resolve(vkr, {"variant.presentation": "reveal"}, _example(vkr), TODAY)

    visible = {f.id for f in next(f for f in ai.forms if f.id == "ai_declaration").fields if f.visible}
    assert {"tools", "usage_table", "pct", "details"} <= visible
    assert [d for d in base.digest.sections if d.section == "documents"] == [
        d for d in ai.digest.sections if d.section == "documents"
    ]
    assert reveal.fingerprint == base.fingerprint
    presentation = next(d for d in reveal.documents if d.id == "presentation")
    assert presentation.source_file == "presentation/reveal/index.html"


# ── Эталоны контракта ────────────────────────────────────────────────────────

_HASH_KEYS = {"fingerprint"}


def _mask(node: Any) -> Any:
    """Хэши в эталонах от прототипа, алгоритм отпечатка определяет `summary.py`: сравниваем их форму, а не значение."""
    if isinstance(node, dict):
        return {k: (_hash_shape(v) if k in _HASH_KEYS and isinstance(v, str) else _mask(v)) for k, v in node.items()}
    if isinstance(node, list):
        return [_mask(item) for item in node]
    return node


def _hash_shape(value: str) -> str:
    assert re.fullmatch(r"[0-9a-f]{12}|[0-9a-f]{16}", value), value
    return f"<hash{len(value)}>"


def _fixture(schema: str, name: str) -> dict[str, Any]:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


_BOUNDARY = ("workspace_id", "pack", "template", "version", "state", "revision", "elapsed_ms")


@pytest.mark.parametrize("name", ["vkr_nda_programmer_only", "coursework_company_cosupervisor"])
def test__golden__fixture_outcomes_are_reproduced_by_the_resolver(repo: YamlTemplateRepository, name: str) -> None:
    fixture = _fixture("PackOutcome", name)
    version = _load(repo, (fixture["pack"], fixture["template"], fixture["version"]))
    example = next(e for e in auto_examples(version) if e.id == fixture["example"])
    include = {k for k in ("checks", "branches") if fixture[k] is not None}

    got = to_json(resolve(version, fixture["inputs"], example, TODAY, include=include))

    for key in _BOUNDARY:
        fixture.pop(key, None)
        got.pop(key, None)
    assert _mask(got) == _mask(fixture)


def test__golden__vkr_fixture_hashes_are_internally_consistent(vkr: TemplateVersion) -> None:
    fixture = _fixture("PackOutcome", "coursework_company_cosupervisor")

    for branch in fixture["branches"]:
        chosen = next(a for a in branch["alternatives"] if a["value"] == branch["chosen"])
        assert chosen["fingerprint"] == fixture["fingerprint"]


def test__golden__inputs_dictionary_equals_the_fixture(vkr: TemplateVersion) -> None:
    fixture = _fixture("PackOutcomeInputs", "vkr")

    got = to_json(inputs_dictionary(vkr, _example(vkr), TODAY))

    assert got["inputs"] == fixture["inputs"]
    assert got["defaults"] == fixture["defaults"]
    PackOutcomeInputsResponse.model_validate({**fixture, "inputs": got["inputs"], "defaults": got["defaults"]})


def test__golden__vkr_documents_per_combination(vkr: TemplateVersion) -> None:
    def states(**combo: str) -> dict[str, str]:
        return {d.id: d.state for d in resolve(vkr, combo, _example(vkr), TODAY, trace=False).documents}

    solo = states()
    assert solo["technical_specification"] == "active"
    assert {
        solo[d] for d in ("shared_technical_specification", "shared_test_program_and_methodology", "annotation")
    } == {"absent"}
    assert (solo["programmer_manual"], solo["operator_manual"], solo["nda"]) == ("active", "active", "inactive")

    research = states(kind="research")
    assert {research[d] for d in ("annotation", "interim_report", "thesis")} == {"active"}
    assert {research[d] for d in ("technical_specification", "programmer_manual", "operator_manual")} == {"absent"}

    team = (
        states(staffing="team3", nda="yes")
        if "nda" in {s.id for s in switches_for(vkr)}
        else states(staffing="team3", **{"meta.nda": "yes"})
    )
    assert (team["shared_technical_specification"], team["shared_test_program_and_methodology"]) == ("active", "active")
    assert team["nda"] == "active"
    only_operator = states(**{"meta.manuals": "Только оператора"})
    assert (only_operator["programmer_manual"], only_operator["operator_manual"]) == ("inactive", "active")


def test__golden__coursework_company_supervisor_routes(coursework: TemplateVersion) -> None:
    def route(**combo: str) -> list[list[str]]:
        outcome = resolve(coursework, combo, _example(coursework), TODAY, trace=False)
        point = next(p for p in outcome.points if p.id == "topic-approval")
        return [[p.persona for p in step] for step in point.route.steps]

    assert route(supervisor="company", co_supervisor="no") == [["author"], ["supervisor"], ["academic_supervisor"]]
    assert route(supervisor="university", co_supervisor="yes") == [["author"], ["supervisor", "co_supervisor"]]
    assert route(supervisor="none") == [["author"], ["supervisor"]]


# ── Случаи без людей, трасса и детерминизм ───────────────────────────────────


def test__no_supervisor__vkr_step_stays_with_an_empty_name_as_the_design_records(vkr: TemplateVersion) -> None:
    outcome = resolve(vkr, {"supervisor": "none"}, _example(vkr), TODAY)

    final = next(p for p in outcome.points if p.id == "final")
    assert [[p.persona for p in step] for step in final.route.steps] == [["author"], ["supervisor"]]
    assert final.route.steps[1][0].name == ""
    assert not next(p for p in outcome.participants if p.persona == "supervisor").present


def test__resolve__is_deterministic_and_does_not_depend_on_the_environment(vkr: TemplateVersion) -> None:
    first = resolve(vkr, {"staffing": "team2"}, _example(vkr), TODAY, include={"checks", "branches"})
    second = resolve(vkr, {"staffing": "team2"}, _example(vkr), TODAY, include={"checks", "branches"})

    assert first == second
    assert to_json(first) == to_json(second)


def test__trace__links_hold_on_every_sampled_combination(vkr: TemplateVersion) -> None:
    for combo in _sample(vkr, 53):
        outcome = resolve(vkr, combo, _example(vkr), TODAY, include={"checks"})
        assert_links(json.loads(json.dumps({"x": 1}) and json.dumps(_body(outcome))))


def _body(outcome: Outcome) -> dict[str, Any]:
    return {"state": "work_tree", **to_json(outcome)}


def test__input_errors__are_reported_with_the_input_and_the_value(vkr: TemplateVersion) -> None:
    from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError

    with pytest.raises(OutcomeInputError) as caught:
        resolve(vkr, {"meta.manuals": "Никакие"}, _example(vkr), TODAY)

    assert (caught.value.field, caught.value.value, caught.value.reason) == (
        "meta.manuals",
        "Никакие",
        "value not allowed",
    )
    assert normalize_inputs(input_specs(vkr), {})["kind"] == "project"


# ── Скорость ─────────────────────────────────────────────────────────────────


def test__speed__a_large_version_resolves_in_milliseconds(vkr: TemplateVersion) -> None:
    example = _example(vkr)
    combos = _sample(vkr, 21)

    def median_ms(**kwargs: Any) -> float:
        times: list[float] = []
        for combo in combos:
            started = time.perf_counter()
            resolve(vkr, combo, example, TODAY, **kwargs)
            times.append((time.perf_counter() - started) * 1000)
        return statistics.median(times)

    plain, traced = median_ms(trace=False), median_ms(trace=True)

    # Запас на медленный CI: на ноутбуке это порядка 1 и 2 мс, предел ловит только провал на порядок.
    assert plain < 50
    assert traced < 100


def test__full_response_for_a_large_version_is_a_valid_contract_body(vkr: TemplateVersion) -> None:
    outcome = resolve(vkr, {}, _example(vkr), TODAY, include={"checks", "branches"})

    PackOutcomeResponse.model_validate(
        {
            "workspace_id": "6f1c1c8e-1b7a-4d51-9a43-0a5b2f3c4d10",
            "pack": "p",
            "template": "t",
            "version": "v",
            "state": "work_tree",
            **to_json(outcome),
        }
    )
    assert outcome.checks
    assert outcome.branches
