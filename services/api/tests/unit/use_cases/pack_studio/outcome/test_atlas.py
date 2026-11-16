"""Атлас результата (срез O4) на реальных версиях и на синтетике: числа дизайна, совпадение строк с прямым `resolve`,
закрепления, пределы, косметика, влияние на элементы, строгие модели контракта и скорость.

Реальные версии: ВКР `hse-cs-se` 2026.1.2 (5184 комбинации вводных, 864 строки атласа, 384 исхода: 24 без участников
и без анкет, 192 с участниками) и курсовая `hse-cs-sse` 2026.1.6 (576 комбинаций, 12 строк, 4 маршрута)."""

from __future__ import annotations

import itertools
import json
import random
import time
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from hse_doc_studio.api.routers.v1.pack_studio_atlas import atlas_response
from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeAtlasResponse
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.atlas import Atlas, AtlasCancelled, AtlasTooLarge, encode_key
from hse_doc_studio.core.pack_studio.outcome.inputs import OutcomeInputError, input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.preview import PreviewExample, auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.atlas import build_atlas, validate_pins
from hse_doc_studio.use_cases.pack_studio.outcome.dictionary import inputs_dictionary
from hse_doc_studio.use_cases.pack_studio.outcome.impact import OutcomeEvaluator, analyze_impact
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve

from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic

_ROOT = Path(__file__).resolve().parents[7]
_FIXTURES = _ROOT / "contracts" / "pack-studio" / "fixtures"
TODAY = date(2026, 11, 16)
VKR = ("hse-cs-se", "vkr", "2026.1.2")
COURSEWORK = ("hse-cs-sse", "coursework", "2026.1.6")


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(_ROOT / "packs")


def _version(repo: YamlTemplateRepository, ref: tuple[str, str, str]) -> TemplateVersion:
    found = repo.get_version(*ref)
    assert found is not None
    return found


@pytest.fixture(scope="module")
def vkr(repo: YamlTemplateRepository) -> TemplateVersion:
    return _version(repo, VKR)


@pytest.fixture(scope="module")
def coursework(repo: YamlTemplateRepository) -> TemplateVersion:
    return _version(repo, COURSEWORK)


def _example(version: TemplateVersion) -> PreviewExample:
    return auto_examples(version)[0]


@pytest.fixture(scope="module")
def vkr_atlas(vkr: TemplateVersion) -> Atlas:
    return build_atlas(vkr, _example(vkr), TODAY, revision="sha256-vkr")


@pytest.fixture(scope="module")
def coursework_atlas(coursework: TemplateVersion) -> Atlas:
    return build_atlas(coursework, _example(coursework), TODAY, revision="sha256-coursework")


def _row_values(atlas: Atlas) -> list[tuple[str, dict[str, str]]]:
    """Строки таблицы как (id исхода, значения измерений)."""
    names = [d.input for d in atlas.dimensions]
    return [(row.outcome, dict(zip(names, row.key.split("|"), strict=True))) for row in atlas.rows]


# ── Числа дизайна на реальных версиях ────────────────────────────────────────


def test__vkr__dimensions_ignored_and_counters_are_the_documented_ones(vkr_atlas: Atlas) -> None:
    assert [d.input for d in vkr_atlas.dimensions] == [
        "kind",
        "staffing",
        "supervisor",
        "co_supervisor",
        "academic_supervisor",
        "meta.manuals",
        "meta.nda",
        "answer.ai_declaration.used_ai",
    ]
    assert {(i.input, i.reason) for i in vkr_atlas.ignored} == {
        ("lang", "cosmetic"),
        ("variant.presentation", "cosmetic"),
    }
    assert vkr_atlas.combinations_total == 5184
    assert vkr_atlas.rows_total == len(vkr_atlas.rows) == 864
    assert vkr_atlas.outcomes_distinct == len(vkr_atlas.outcomes) == 384


def test__vkr__distinct_outcomes_by_what_they_include(vkr_atlas: Atlas) -> None:
    # Документы, точки и маршрут; затем участники; затем анкеты (раздел 4.9 дизайна).
    assert vkr_atlas.distinct_by(["documents", "points", "route"]) == 24
    assert vkr_atlas.distinct_by(["documents", "points", "route", "participants"]) == 192
    assert vkr_atlas.distinct_by(["documents", "points", "route", "participants", "forms"]) == 384
    assert sum(o.rows for o in vkr_atlas.outcomes) == 864


def test__vkr__affects_per_dimension_are_exact(vkr_atlas: Atlas) -> None:
    affects = {d.input: set(d.affects) for d in vkr_atlas.dimensions}

    assert affects["answer.ai_declaration.used_ai"] == {"forms"}
    assert affects["supervisor"] == affects["co_supervisor"] == affects["academic_supervisor"] == {"participants"}
    assert affects["meta.nda"] == {"documents", "points"}
    assert affects["meta.manuals"] == {"documents", "points", "route"}
    assert affects["staffing"] == {"documents", "participants", "points", "route"}
    assert affects["kind"] == {"documents", "meta", "points", "route"}


def test__coursework__four_routes_one_set_of_documents(coursework_atlas: Atlas) -> None:
    atlas = coursework_atlas

    assert (atlas.combinations_total, atlas.rows_total, atlas.outcomes_distinct) == (576, 12, 12)
    assert atlas.distinct_by(["route"]) == 4
    assert atlas.distinct_by(["documents"]) == 1
    assert [d.input for d in atlas.dimensions] == ["supervisor", "co_supervisor", "academic_supervisor"]
    assert {(i.input, i.reason) for i in atlas.ignored} == {
        ("lang", "cosmetic"),
        ("kind", "no_effect"),
        ("staffing", "no_effect"),
        ("meta.proposal_stage", "no_effect"),
        ("meta.report_margins", "no_effect"),
        ("variant.presentation", "cosmetic"),
    }


def test__coursework__matches_the_contract_fixture_but_for_hashes(coursework_atlas: Atlas) -> None:
    fixture = json.loads((_FIXTURES / "PackOutcomeAtlas" / "coursework.json").read_text(encoding="utf-8"))

    assert [d.input for d in coursework_atlas.dimensions] == [d["input"] for d in fixture["dimensions"]]
    assert [(d.input, list(d.values), d.default, list(d.affects)) for d in coursework_atlas.dimensions] == [
        (d["input"], d["values"], d["default"], d["affects"]) for d in fixture["dimensions"]
    ]
    assert [[to_json(r) for r in d.rules] for d in coursework_atlas.dimensions] == [
        d["rules"] for d in fixture["dimensions"]
    ]
    assert [to_json(i) for i in coursework_atlas.ignored] == fixture["ignored"]
    assert [(r.key, r.outcome) for r in coursework_atlas.rows] == [(r["key"], r["outcome"]) for r in fixture["rows"]]
    assert [o.rows for o in coursework_atlas.outcomes] == [o["rows"] for o in fixture["outcomes"]]
    for got, want in zip(coursework_atlas.outcomes, fixture["outcomes"], strict=True):
        assert to_json(got.digest)["documents"] == want["digest"]["documents"]
        assert to_json(got.digest)["participants"] == want["digest"]["participants"]
        assert to_json(got.digest)["points"] == want["digest"]["points"]
        assert to_json(got.digest)["meta_visible"] == want["digest"]["meta_visible"]


# ── Каждая строка равна прямому расчёту ──────────────────────────────────────


def _defaults(version: TemplateVersion) -> dict[str, str]:
    return normalize_inputs(input_specs(version), {})


def test__rows__every_row_of_the_coursework_equals_a_direct_resolve(
    coursework: TemplateVersion, coursework_atlas: Atlas
) -> None:
    by_id = {o.id: o for o in coursework_atlas.outcomes}
    base = _defaults(coursework)

    for outcome_id, values in _row_values(coursework_atlas):
        direct = resolve(coursework, {**base, **values}, _example(coursework), TODAY, trace=False)
        assert direct.fingerprint == by_id[outcome_id].fingerprint, values
        assert direct.digest == by_id[outcome_id].digest, values


def test__rows__every_combination_of_the_coursework_lands_on_the_outcome_of_its_row(
    coursework: TemplateVersion, coursework_atlas: Atlas
) -> None:
    """Полнота измерений: любая из 576 комбинаций даёт тот же результат, что строка её значений измерений."""
    atlas = coursework_atlas
    by_key = {row.key: next(o for o in atlas.outcomes if o.id == row.outcome) for row in atlas.rows}
    specs = input_specs(coursework)
    checked = 0
    for values in itertools.product(*(spec.values for spec in specs)):
        combo = {spec.id: value for spec, value in zip(specs, values, strict=True)}
        key = encode_key(combo[d.input] for d in atlas.dimensions)
        got = resolve(coursework, combo, _example(coursework), TODAY, trace=False)
        assert got.fingerprint == by_key[key].fingerprint, combo
        checked += 1

    assert checked == atlas.combinations_total == 576


def test__rows__random_rows_and_random_combinations_of_the_vkr_equal_a_direct_resolve(
    vkr: TemplateVersion, vkr_atlas: Atlas
) -> None:
    rng = random.Random(20261116)  # noqa: S311 — детерминированная выборка теста
    by_id = {o.id: o for o in vkr_atlas.outcomes}
    base = _defaults(vkr)
    for outcome_id, values in rng.sample(_row_values(vkr_atlas), 120):
        direct = resolve(vkr, {**base, **values}, _example(vkr), TODAY, trace=False)
        assert direct.fingerprint == by_id[outcome_id].fingerprint, values
        assert direct.digest == by_id[outcome_id].digest, values

    # Полнота: комбинации с изменёнными косметическими и «не влияющими» вводными попадают в ту же строку.
    specs = input_specs(vkr)
    by_key = {row.key: by_id[row.outcome] for row in vkr_atlas.rows}
    for _ in range(200):
        combo = {spec.id: rng.choice(spec.values) for spec in specs}
        key = encode_key(combo[d.input] for d in vkr_atlas.dimensions)
        assert resolve(vkr, combo, _example(vkr), TODAY, trace=False).fingerprint == by_key[key].fingerprint, combo


# ── Закрепления ──────────────────────────────────────────────────────────────


def test__pin__cuts_the_table_and_keeps_the_pinned_input_as_a_one_valued_dimension(
    vkr: TemplateVersion, vkr_atlas: Atlas
) -> None:
    pinned = build_atlas(vkr, _example(vkr), TODAY, pins={"kind": "research", "meta.nda": "yes"})

    assert [d.input for d in pinned.dimensions] == [d.input for d in vkr_atlas.dimensions]
    kind = next(d for d in pinned.dimensions if d.input == "kind")
    assert (list(kind.values), kind.default) == (["research"], "research")
    assert pinned.rows_total == 864 // 2 // 2
    assert pinned.combinations_total == vkr_atlas.combinations_total
    # Строки закреплённого атласа это подмножество строк полного, исходы по ним те же.
    full = {r.key: next(o for o in vkr_atlas.outcomes if o.id == r.outcome).fingerprint for r in vkr_atlas.rows}
    for row in pinned.rows:
        fingerprint = next(o for o in pinned.outcomes if o.id == row.outcome).fingerprint
        assert full[row.key] == fingerprint
    assert all(row.key.startswith("research|") for row in pinned.rows)


def test__pin__of_an_ignored_input_changes_nothing_in_the_table(
    coursework: TemplateVersion, coursework_atlas: Atlas
) -> None:
    pinned = build_atlas(coursework, _example(coursework), TODAY, pins={"lang": "en"})

    assert [(r.key, r.outcome) for r in pinned.rows] == [(r.key, r.outcome) for r in coursework_atlas.rows]
    assert [i.input for i in pinned.ignored] == [i.input for i in coursework_atlas.ignored]


def test__pin__with_every_dimension_pinned_is_one_row(coursework: TemplateVersion) -> None:
    pins = {"supervisor": "company", "co_supervisor": "yes", "academic_supervisor": "no"}

    atlas = build_atlas(coursework, _example(coursework), TODAY, pins=pins)

    assert [(r.key, r.outcome) for r in atlas.rows] == [("company|yes|no", "o1")]
    assert atlas.outcomes_distinct == 1


@pytest.mark.parametrize(
    ("pins", "field", "reason"),
    [
        ({"nope": "x"}, "nope", "unknown input"),
        ({"supervisor": "boss"}, "supervisor", "value is not one of the input's values"),
    ],
)
def test__pin__an_unknown_input_or_value_is_an_input_error(
    coursework: TemplateVersion, pins: dict[str, str], field: str, reason: str
) -> None:
    with pytest.raises(OutcomeInputError) as caught:
        build_atlas(coursework, _example(coursework), TODAY, pins=pins)

    assert (caught.value.field, caught.value.reason) == (field, reason)
    with pytest.raises(OutcomeInputError):
        validate_pins(input_specs(coursework), pins)


# ── Пределы и срок ───────────────────────────────────────────────────────────


def test__limit__a_table_over_the_limit_is_atlas_too_large_with_the_row_count(vkr: TemplateVersion) -> None:
    with pytest.raises(AtlasTooLarge) as caught:
        build_atlas(vkr, _example(vkr), TODAY, limit=863)

    assert (caught.value.rows, caught.value.limit) == (864, 863)


def _switching_forms(tmp_path: Path) -> TemplateVersion:
    """Версия с одиннадцатью ответами анкеты, каждый из которых включает своё поле: 11 измерений поверх трёх
    руководителей, 49152 комбинации вводных (больше предела перебора) и 24576 строк атласа."""
    switches = "\n".join(
        f"          - {{ id: c{i}, type: bool, label: {{ ru: C{i}, en: C{i} }} }}\n"
        f"          - {{ id: d{i}, type: text, label: {{ ru: D{i}, en: D{i} }}, "
        f"visible_if: {{ field: c{i}, equals: true }} }}"
        for i in range(11)
    )
    return load_synthetic(
        tmp_path,
        version_yaml=f"""\
id: "1.0.0"
status: beta
langs: [ru]
documents:
  - {{ id: report, name: {{ ru: Отчёт, en: Report }}, source_file: report/report.tex, output_file: report/report.pdf }}
forms:
  - id: f
    title: {{ ru: Форма, en: Form }}
    sections:
      - id: s
        title: {{ ru: Раздел, en: Section }}
        fields:
{switches}
""",
        checks_yaml=None,
    )


def test__limit__a_synthetic_version_with_many_dimensions_exceeds_the_default_limit(tmp_path: Path) -> None:
    version = _switching_forms(tmp_path)

    with pytest.raises(AtlasTooLarge) as caught:
        build_atlas(version, _example(version), TODAY)

    assert (caught.value.rows, caught.value.limit) == (24576, 2000)


def test__limit__pins_cut_a_too_large_table_and_the_neighbour_mode_still_finds_every_dimension(tmp_path: Path) -> None:
    version = _switching_forms(tmp_path)
    pins = {"answer.f.c0": "yes", "supervisor": "company", "co_supervisor": "yes", "academic_supervisor": "no"}

    atlas = build_atlas(version, _example(version), TODAY, pins=pins)

    assert atlas.combinations_total == 49152
    assert atlas.rows_total == 1024
    assert atlas.outcomes_distinct == 1024
    assert len(atlas.dimensions) == 3 + 11
    specs = input_specs(version)
    analysis = analyze_impact(OutcomeEvaluator(version, specs, _example(version), TODAY), specs, _defaults(version))
    assert not analysis.exact
    assert {i for i, impact in analysis.impacts.items() if impact.effective} == {d.input for d in atlas.dimensions}


def test__deadline__a_check_that_raises_stops_the_whole_calculation(coursework: TemplateVersion) -> None:
    calls: list[int] = []

    def check() -> None:
        calls.append(1)
        if len(calls) > 5:
            raise AtlasCancelled

    with pytest.raises(AtlasCancelled):
        build_atlas(coursework, _example(coursework), TODAY, check=check)

    assert len(calls) == 6


# ── Влияние на элементы, соседи и перебор ────────────────────────────────────


def test__impact__elements_changed_by_an_input_are_named_by_the_contract_ids(
    coursework: TemplateVersion,
) -> None:
    specs = input_specs(coursework)
    analysis = analyze_impact(
        OutcomeEvaluator(coursework, specs, _example(coursework), TODAY), specs, _defaults(coursework)
    )

    co = analysis.impacts["co_supervisor"]
    assert analysis.exact
    assert ("participants", "participant", "co_supervisor") in co.elements
    assert any(section == "route" and kind == "route_step" for section, kind, _ in co.elements)
    assert analysis.impacts["lang"].elements == ()
    assert analysis.impacts["lang"].cosmetic
    assert not analysis.impacts["kind"].cosmetic
    # Каждый затронутый элемент лежит в затронутом разделе и наоборот.
    for impact in analysis.impacts.values():
        assert {section for section, _, _ in impact.elements} == set(impact.sections)


def test__impact__the_neighbour_mode_agrees_with_the_exhaustive_one_on_the_real_versions(
    vkr: TemplateVersion, coursework: TemplateVersion
) -> None:
    for version in (vkr, coursework):
        specs = input_specs(version)
        defaults = _defaults(version)
        evaluator = OutcomeEvaluator(version, specs, _example(version), TODAY)
        near = analyze_impact(evaluator, specs, defaults, force=False)
        exact = analyze_impact(evaluator, specs, defaults, force=True)

        assert not near.exact
        assert exact.exact
        assert exact.combinations == (5184 if version is vkr else 576)
        assert near.combinations < exact.combinations
        assert {k: v.sections for k, v in near.impacts.items()} == {k: v.sections for k, v in exact.impacts.items()}


def test__impact__the_neighbour_mode_never_invents_an_effect_on_the_synthetic_version(tmp_path: Path) -> None:
    version = load_synthetic(tmp_path)
    specs = input_specs(version)
    defaults = _defaults(version)
    evaluator = OutcomeEvaluator(version, specs, _example(version), TODAY)

    near = analyze_impact(evaluator, specs, defaults, force=False)
    exact = analyze_impact(evaluator, specs, defaults, force=True)

    for input_id, impact in near.impacts.items():
        assert set(impact.sections) <= set(exact.impacts[input_id].sections)
        assert set(impact.elements) <= set(exact.impacts[input_id].elements)


def test__dictionary__affects_use_the_shared_analysis_and_accept_a_ready_one(coursework: TemplateVersion) -> None:
    specs = input_specs(coursework)
    exact = analyze_impact(
        OutcomeEvaluator(coursework, specs, _example(coursework), TODAY), specs, _defaults(coursework), force=True
    )

    cheap = inputs_dictionary(coursework, _example(coursework), TODAY)
    ready = inputs_dictionary(coursework, _example(coursework), TODAY, analysis=exact)

    assert {i.id: i.affects for i in cheap.inputs} == {i.id: i.affects for i in ready.inputs}
    assert {i.id: i.affects for i in cheap.inputs}["co_supervisor"] == ("participants", "route")


# ── Контракт ─────────────────────────────────────────────────────────────────


def _body(atlas: Atlas) -> dict[str, Any]:
    return json.loads(
        atlas_response(
            UUID("6f1c1c8e-1b7a-4d51-9a43-0a5b2f3c4d10"), "p", "t", "1.0.0", "work_tree", atlas
        ).model_dump_json()
    )


@pytest.mark.parametrize("which", ["vkr_atlas", "coursework_atlas"])
def test__contract__the_atlas_is_accepted_by_the_strict_model(which: str, request: pytest.FixtureRequest) -> None:
    atlas: Atlas = request.getfixturevalue(which)

    body = _body(atlas)

    PackOutcomeAtlasResponse.model_validate(body)
    assert body["rows_total"] == len(body["rows"])
    assert body["outcomes_distinct"] == len(body["outcomes"])
    assert {r["outcome"] for r in body["rows"]} == {o["id"] for o in body["outcomes"]}
    assert all(len(r["key"].split("|")) == len(body["dimensions"]) for r in body["rows"])
    assert body["revision"] == atlas.revision


def test__contract__the_fixture_is_read_back_into_the_same_shape(coursework_atlas: Atlas) -> None:
    fixture = json.loads((_FIXTURES / "PackOutcomeAtlas" / "coursework.json").read_text(encoding="utf-8"))
    body = _body(coursework_atlas)

    assert set(body) == set(fixture)
    assert set(body["dimensions"][0]) == set(fixture["dimensions"][0])
    assert set(body["outcomes"][0]) == set(fixture["outcomes"][0])
    assert set(body["outcomes"][0]["digest"]) == set(fixture["outcomes"][0]["digest"])


def test__contract__every_row_key_has_a_value_of_its_dimension(vkr_atlas: Atlas) -> None:
    allowed = [set(d.values) for d in vkr_atlas.dimensions]

    for row in vkr_atlas.rows:
        parts = row.key.split("|")
        assert all(part in values for part, values in zip(parts, allowed, strict=True)), row.key


# ── Скорость ─────────────────────────────────────────────────────────────────


def test__performance__real_versions_build_within_the_service_deadline(
    vkr: TemplateVersion, coursework: TemplateVersion, capsys: pytest.CaptureFixture[str]
) -> None:
    started = time.perf_counter()
    small = build_atlas(coursework, _example(coursework), TODAY)
    small_s = time.perf_counter() - started
    started = time.perf_counter()
    big = build_atlas(vkr, _example(vkr), TODAY)
    big_s = time.perf_counter() - started
    size = len(json.dumps(_body(big), ensure_ascii=False).encode())

    with capsys.disabled():
        print(  # noqa: T201 — цифры для отчёта среза
            f"\n[atlas] coursework {small.rows_total} rows {small_s:.2f}s; vkr {big.rows_total} rows {big_s:.2f}s, "
            f"json {size / 1024:.0f} KiB"
        )
    # Предел сервиса 20 с; тест держит запас вдвое: выше значит, что расчёт стал в разы дороже.
    assert small_s < 5
    assert big_s < 40
