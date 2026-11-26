"""Сравнения результатов на реальных версиях: два набора вводных, два сценария, «до и после» правки и матрица (O7).

Версии настоящие: ВКР, курсовой проект и практика `hse-cs-se`, курсовой проект `hse-cs-sse`; сценарии стартовые, из
паков. Каждый ответ сверяется с независимым расчётом: прямой `resolve` обеих сторон и множества документов, участников,
пунктов, шагов и пар маршрута (раздел 10 дизайна: правка условия даёт ожидаемые `+`, `~`, `-`)."""

from __future__ import annotations

import itertools
import json
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import (
    PackOutcomeCompareResponse,
    PackOutcomeImpactResponse,
    PackOutcomeMatrixResponse,
)
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.atlas import decode_key
from hse_doc_studio.core.pack_studio.outcome.compare import diff_outcomes, section_deltas
from hse_doc_studio.core.pack_studio.outcome.inputs import input_specs
from hse_doc_studio.core.pack_studio.outcome.model import Outcome
from hse_doc_studio.core.pack_studio.outcome.points import pair_id
from hse_doc_studio.core.pack_studio.outcome.scenario_check import Change
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    DocumentStateAssertion,
    Scenario,
)
from hse_doc_studio.core.pack_studio.outcome.summary import full_fingerprint
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.compare import (
    Side,
    SideInputError,
    atlas_impact,
    compare_body,
    compare_sides,
    impact_body,
    matrix_body,
    matrix_rows,
    resolve_side,
    scenario_impacts,
)
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve

from tests.unit.use_cases.pack_studio.outcome import compare_support as cs
from tests.unit.use_cases.pack_studio.outcome.compare_support import (
    COURSEWORK,
    COURSEWORK_SE,
    FIXTURES,
    PACKS,
    PRACTICE,
    TODAY,
    VKR,
    applicable_scenarios_of,
    example_of,
    load,
    scenarios_of,
    side_of,
)


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(PACKS)


@pytest.fixture(scope="module")
def coursework(repo: YamlTemplateRepository) -> TemplateVersion:
    return load(repo, COURSEWORK)


@pytest.fixture(scope="module")
def edited(tmp_path_factory: pytest.TempPathFactory) -> TemplateVersion:
    return cs.edited_coursework(tmp_path_factory.mktemp("edited-coursework"))


def _resolve(version: TemplateVersion, inputs: Mapping[str, str], *, checks: bool = True) -> Outcome:
    include = {"checks"} if checks else set()
    return resolve(version, inputs, example_of(version), TODAY, include=include)


# ── Независимый расчёт: что изменилось, по множествам, без индекса элементов ────


def _sets(outcome: Outcome) -> dict[str, Any]:
    return {
        "documents": {d.id for d in outcome.documents if d.state == "active"},
        "participants": {p.persona for p in outcome.participants if p.present},
        "items": {(pt.id, i.doc_id) for pt in outcome.points for i in pt.items if i.active},
        "steps": {
            (pt.id, n): tuple(sorted(p.persona for p in step))
            for pt in outcome.points
            for n, step in enumerate(pt.route.steps, start=1)
        },
        "pairs": {(pt.id, p.doc_id, p.slot_id, p.persona) for pt in outcome.points for p in pt.route.pairs},
        "skipped": {(pt.id, s.doc_id, s.slot_id) for pt in outcome.points for s in pt.route.skipped},
    }


def _symbols(changes: Iterable[Change], section: str, kind: str) -> dict[str, str]:
    return {c.id: c.symbol for c in changes if c.section == section and c.kind == kind}


def _assert_matches_independent(before: Outcome, after: Outcome, changes: tuple[Change, ...]) -> None:
    """Знаки `+` и `-` совпадают с разностью множеств, посчитанных прямо по результатам."""
    old, new = _sets(before), _sets(after)
    plus_minus = {
        ("documents", "document"): (old["documents"], new["documents"]),
        ("participants", "participant"): (old["participants"], new["participants"]),
    }
    for (section, kind), (left, right) in plus_minus.items():
        symbols = _symbols(changes, section, kind)
        # В комплекте или нет: `+` вошёл, `-` вышел; `~` у документов бывает только между `inactive` и `absent`.
        assert {i for i, s in symbols.items() if s == "+"} == right - left, (section, kind)
        assert {i for i, s in symbols.items() if s == "-"} == left - right, (section, kind)
    items = _symbols(changes, "points", "item")
    assert {i for i, s in items.items() if s == "+"} == {f"{p}/{d}" for p, d in new["items"] - old["items"]}
    assert {i for i, s in items.items() if s == "-"} == {f"{p}/{d}" for p, d in old["items"] - new["items"]}
    steps = _symbols(changes, "route", "route_step")
    keys = {*old["steps"], *new["steps"]}
    differing = {f"{p}/step/{n}" for p, n in keys if old["steps"].get((p, n)) != new["steps"].get((p, n))}
    assert set(steps) == differing
    for (point, number), personas in new["steps"].items():
        if (point, number) not in old["steps"]:
            assert steps[f"{point}/step/{number}"] == "+"
        elif old["steps"][(point, number)] != personas:
            assert steps[f"{point}/step/{number}"] == "~"
    pairs = _symbols(changes, "route", "route_pair")
    assert {i for i, s in pairs.items() if s == "+"} == {pair_id(*key) for key in new["pairs"] - old["pairs"]}
    assert {i for i, s in pairs.items() if s == "-"} == {pair_id(*key) for key in old["pairs"] - new["pairs"]}
    skipped = _symbols(changes, "route", "skipped_pair")
    assert {i for i, s in skipped.items() if s == "+"} == {
        f"{p}/{d}/{s}" for p, d, s in new["skipped"] - old["skipped"]
    }
    assert {i for i, s in skipped.items() if s == "-"} == {
        f"{p}/{d}/{s}" for p, d, s in old["skipped"] - new["skipped"]
    }


# ── Две стороны на одном состоянии ────────────────────────────────────────────


_TEMPLATES = (VKR, COURSEWORK_SE, PRACTICE, COURSEWORK)


@pytest.mark.parametrize("ref", _TEMPLATES, ids=lambda r: "/".join(r))
def test__compare__every_pair_of_starter_scenarios_matches_an_independent_resolve(
    repo: YamlTemplateRepository, ref: tuple[str, str, str]
) -> None:
    version = load(repo, ref)
    scenarios = applicable_scenarios_of(ref)
    assert len(scenarios) >= 2
    example = example_of(version)

    for (left_id, left), (right_id, right) in itertools.combinations(scenarios.items(), 2):
        comparison = compare_sides(Side(version, example, left.inputs), Side(version, example, right.inputs), TODAY)

        before, after = _resolve(version, left.inputs), _resolve(version, right.inputs)
        assert comparison.left.fingerprint == full_fingerprint(before), (left_id, right_id)
        assert comparison.right.fingerprint == full_fingerprint(after)
        assert comparison.identical is (full_fingerprint(before) == full_fingerprint(after)), (left_id, right_id)
        _assert_matches_independent(before, after, comparison.changes)
        assert comparison.summary == section_deltas(comparison.changes)


def test__compare__university_against_company_gives_the_known_route_changes(coursework: TemplateVersion) -> None:
    scenarios = scenarios_of(COURSEWORK)
    example = example_of(coursework)

    comparison = compare_sides(
        Side(coursework, example, scenarios["university-supervisor"].inputs),
        Side(coursework, example, scenarios["company-supervisor"].inputs),
        TODAY,
    )

    got = {(c.symbol, c.section, c.kind, c.id) for c in comparison.changes}
    assert got == {
        ("+", "participants", "participant", "co_supervisor"),
        ("~", "route", "route_step", "topic-approval/step/2"),
        ("+", "route", "route_step", "topic-approval/step/3"),
        ("+", "route", "route_pair", "topic-approval/topic_application/co_supervisor"),
        ("+", "route", "route_pair", "topic-approval/topic_application/academic_supervisor"),
        ("-", "route", "skipped_pair", "topic-approval/topic_application/co_supervisor"),
        ("-", "route", "skipped_pair", "topic-approval/topic_application/academic_supervisor"),
    }
    step = next(c for c in comparison.changes if c.id == "topic-approval/step/2")
    assert (step.before, step.after) == ("supervisor", "supervisor, co_supervisor")


def test__compare__changes_carry_the_rules_that_flipped(coursework: TemplateVersion) -> None:
    scenarios = scenarios_of(COURSEWORK)
    example = example_of(coursework)

    comparison = compare_sides(
        Side(coursework, example, scenarios["university-supervisor"].inputs),
        Side(coursework, example, scenarios["company-supervisor"].inputs),
        TODAY,
    )

    pair = next(
        c
        for c in comparison.changes
        if c.id == "topic-approval/topic_application/academic_supervisor" and c.kind == "route_pair"
    )
    (reason,) = pair.why
    assert reason.kind == "slot_when"
    assert (reason.before, reason.after) == ("not_held", "held")
    assert reason.rule.pointer == "/pack_submission/profiles/0/signing_slots/1/when"
    assert reason.before_actual["supervisor.role"] == "university"
    assert reason.after_actual["supervisor.role"] == "company"
    # Правило с обеих сторон: условие то же, значения разные.
    assert [(t.op, t.subject) for t in reason.terms][0][1].startswith("supervisor")
    assert all(len(c.why) <= 6 for c in comparison.changes)
    # Причину у шага без собственных решений даёт цепочка пар его людей.
    step = next(c for c in comparison.changes if c.id == "topic-approval/step/3")
    assert {r.kind for r in step.why} >= {"slot_when"}


def test__compare__same_inputs_are_identical_and_the_other_way_round_flips_the_symbols(
    coursework: TemplateVersion,
) -> None:
    example = example_of(coursework)
    a, b = {"supervisor": "university", "co_supervisor": "no"}, {"supervisor": "company", "co_supervisor": "yes"}

    same = compare_sides(Side(coursework, example, a), Side(coursework, example, a), TODAY)
    forward = compare_sides(Side(coursework, example, a), Side(coursework, example, b), TODAY)
    backward = compare_sides(Side(coursework, example, b), Side(coursework, example, a), TODAY)

    assert same.identical
    assert same.changes == ()
    flip = {"+": "-", "-": "+", "~": "~"}
    assert {(flip[c.symbol], c.section, c.kind, c.id) for c in forward.changes} == {
        (c.symbol, c.section, c.kind, c.id) for c in backward.changes
    }
    for c in forward.changes:
        mirrored = next(x for x in backward.changes if (x.section, x.kind, x.id) == (c.section, c.kind, c.id))
        if c.symbol == "~":
            assert (c.before, c.after) == (mirrored.after, mirrored.before)


def test__compare__equal_fingerprints_mean_no_changes_over_all_combinations(coursework: TemplateVersion) -> None:
    """Инвариант на всём пространстве вводных курсового проекта: отпечаток равен, значит изменений нет, и наоборот."""
    example = example_of(coursework)
    specs = input_specs(coursework)
    base = _resolve(coursework, {})
    combos = [{spec.id: value} for spec in specs for value in spec.values]

    for combo in combos:
        other = _resolve(coursework, combo)
        changes = diff_outcomes(base, other, reasons=False)
        assert (full_fingerprint(base) == full_fingerprint(other)) is (not changes), combo
        assert section_deltas(changes) == section_deltas(diff_outcomes(base, other)), combo
    assert example.id


def test__compare__vkr_team_against_solo_shows_documents_and_participants(repo: YamlTemplateRepository) -> None:
    vkr = load(repo, VKR)
    scenarios = scenarios_of(VKR)
    example = example_of(vkr)

    comparison = compare_sides(
        Side(vkr, example, scenarios["solo-university-supervisor"].inputs),
        Side(vkr, example, scenarios["team-of-three-nda"].inputs),
        TODAY,
    )

    got = {(c.symbol, c.id) for c in comparison.changes if c.kind == "document"}
    assert ("+", "shared_technical_specification") in got
    assert ("+", "nda") in got
    participants = _symbols(comparison.changes, "participants", "participant")
    # Персоны автора переименованы (R11): в одиночной работе `author`, в команде `author1`, `author2`, `author3`.
    assert participants == {"author": "-", "author1": "+", "author2": "+", "author3": "+"}
    doc = next(c for c in comparison.changes if c.kind == "document" and c.id == "technical_specification")
    assert doc.symbol == "~"
    assert "author1" in (doc.after or "")
    assert "author3" in (doc.after or "")


def test__compare__inputs_invalid_on_a_side_names_the_side(coursework: TemplateVersion) -> None:
    example = example_of(coursework)

    with pytest.raises(SideInputError) as raised:
        compare_sides(Side(coursework, example, {}), Side(coursework, example, {"kind": "nope"}), TODAY)

    assert (raised.value.side, raised.value.field) == ("right", "kind")
    with pytest.raises(SideInputError) as left:
        compare_sides(Side(coursework, example, {"nope": "x"}), Side(coursework, example, {}), TODAY)
    assert left.value.side == "left"


# ── «До и после»: правка условия слота и документа ───────────────────────────


def test__impact__slot_edit_changes_exactly_the_scenarios_it_should(
    coursework: TemplateVersion, edited: TemplateVersion
) -> None:
    scenarios = scenarios_of(COURSEWORK)

    impacts = scenario_impacts(side_of(coursework), side_of(edited), scenarios, TODAY)

    statuses = {i.scenario: i.status for i in impacts}
    # Считаются сценарии, которым версия подходит по `versions`; сценарии другой линии версий в ответ не входят.
    assert list(statuses) == list(applicable_scenarios_of(COURSEWORK))
    assert {s: statuses[s] for s in ("company-supervisor", "no-supervisor", "university-supervisor")} == {
        "company-supervisor": "unchanged",
        "no-supervisor": "unchanged",
        "university-supervisor": "changed",
    }
    changed = next(i for i in impacts if i.scenario == "university-supervisor")
    # Ручной расчёт: после правки слот академического руководителя нужен любому научруку, то есть у научрука из ВШЭ
    # шаг 3 появляется, пара появляется, пропуск исчезает.
    assert {(c.symbol, c.kind, c.id) for c in changed.changes} == {
        ("+", "route_step", "topic-approval/step/3"),
        ("+", "route_pair", "topic-approval/topic_application/academic_supervisor"),
        ("-", "skipped_pair", "topic-approval/topic_application/academic_supervisor"),
    }
    before = _resolve(coursework, scenarios["university-supervisor"].inputs)
    after = _resolve(edited, scenarios["university-supervisor"].inputs)
    assert [[p.persona for p in s] for s in before.points[0].route.steps] == [["author"], ["supervisor"]]
    assert [[p.persona for p in s] for s in after.points[0].route.steps] == [
        ["author"],
        ["supervisor"],
        ["academic_supervisor"],
    ]
    reason = next(c for c in changed.changes if c.kind == "route_pair").why[0]
    assert (reason.kind, reason.before, reason.after) == ("slot_when", "not_held", "held")
    assert section_deltas(changed.changes)[0].section == "route"


def test__impact__atlas_rows_changed_equal_a_brute_force_count(
    coursework: TemplateVersion, edited: TemplateVersion
) -> None:
    now = cs._atlas(edited, example_of(edited))
    was = cs._atlas(coursework, example_of(coursework))

    summary = atlas_impact(now, was, coursework, example_of(coursework), TODAY)

    dims = [d["input"] for d in now["dimensions"]]
    brute = 0
    for row in now["rows"]:
        inputs = dict(zip(dims, decode_key(row["key"]), strict=True))
        if full_fingerprint_of(coursework, inputs, checks=False) != full_fingerprint_of(edited, inputs, checks=False):
            brute += 1
    assert summary["rows_changed"] == brute > 0
    assert summary["rows_total"] == len(now["rows"])
    assert (summary["outcomes_before"], summary["outcomes_after"]) == (
        was["outcomes_distinct"],
        now["outcomes_distinct"],
    )
    assert summary["outcomes_after"] < summary["outcomes_before"]


def full_fingerprint_of(version: TemplateVersion, inputs: Mapping[str, str], *, checks: bool) -> str:
    return full_fingerprint(_resolve(version, inputs, checks=checks))


def test__impact__document_condition_edit_in_vkr(tmp_path: Path, repo: YamlTemplateRepository) -> None:
    real = load(repo, VKR)
    root = cs.copy_template(tmp_path, VKR)
    cs.edit_manifest(
        root,
        VKR,
        "supported_kinds:\n- research\n",
        "supported_kinds:\n- research\n- project\n",
        name="files/shared_annotation/doc.yaml",
    )
    edited_vkr = load(YamlTemplateRepository(root), VKR)
    scenarios = scenarios_of(VKR)

    impacts = {i.scenario: i for i in scenario_impacts(side_of(real), side_of(edited_vkr), scenarios, TODAY)}

    assert list(impacts) == list(applicable_scenarios_of(VKR))
    # Общая аннотация команды теперь нужна и проектам: из этих сценариев меняется только команда из трёх.
    named = (
        "nda-programmer-manual-only",
        "research-company-supervisor",
        "solo-university-supervisor",
        "team-of-three-nda",
    )
    assert {s: impacts[s].status for s in named} == {
        "nda-programmer-manual-only": "unchanged",
        "research-company-supervisor": "unchanged",
        "solo-university-supervisor": "unchanged",
        "team-of-three-nda": "changed",
    }
    changes = {(c.symbol, c.section, c.id) for c in impacts["team-of-three-nda"].changes}
    assert ("+", "documents", "shared_annotation") in changes
    assert any(sym == "+" and sec == "points" for sym, sec, _ in changes)
    doc = next(c for c in impacts["team-of-three-nda"].changes if c.id == "shared_annotation")
    assert (doc.before, doc.after) == ("absent", "active")
    why = doc.why
    assert why
    assert any(r.kind == "supported_kinds" and (r.before, r.after) == ("not_held", "held") for r in why)


def test__impact__scenario_that_cannot_be_read_on_a_side_is_an_error_with_the_side_named(
    coursework: TemplateVersion,
) -> None:
    broken = Scenario(name={"ru": "Сломан", "en": "Broken"}, inputs={"no_such_input": "x"})
    scenarios: dict[str, Scenario | str] = {
        "broken": broken,
        "unreadable": "assertions[0].kind: unknown kind",
        "fine": scenarios_of(COURSEWORK)["no-supervisor"],
    }

    impacts = {i.scenario: i for i in scenario_impacts(side_of(coursework), side_of(coursework), scenarios, TODAY)}

    assert impacts["broken"].status == "error"
    assert impacts["broken"].message is not None
    assert impacts["broken"].message.startswith("base: no_such_input")
    assert "work_tree: no_such_input" in impacts["broken"].message
    assert (impacts["unreadable"].status, impacts["unreadable"].message) == (
        "error",
        "assertions[0].kind: unknown kind",
    )
    assert impacts["fine"].status == "unchanged"
    body = impact_body(list(impacts.values()), None)
    assert body["summary"]["scenarios_error"] == 2
    assert body["summary"]["atlas"] is None


def test__impact__input_that_exists_only_in_the_new_version_breaks_that_scenario_not_the_run(
    tmp_path: Path, coursework: TemplateVersion
) -> None:
    root = cs.copy_template(tmp_path, COURSEWORK)
    # Новая версия получила вводную: поле select с вариантами. На базе её нет.
    cs.edit_manifest(
        root,
        COURSEWORK,
        "meta_fields:\n",
        "meta_fields:\n  extra_mode: { type: select, label: { ru: Режим, en: Mode }, options: [a, b], default: a }\n",
    )
    edited = load(YamlTemplateRepository(root), COURSEWORK)
    scenario = Scenario(name={"ru": "С новой вводной", "en": "New input"}, inputs={"meta.extra_mode": "b"})

    impacts = scenario_impacts(side_of(coursework), side_of(edited), {"new-input": scenario}, TODAY)

    assert impacts[0].status == "error"
    assert (impacts[0].message or "").startswith("base:")
    assert "work_tree" not in (impacts[0].message or "")


def test__impact__scenario_outside_its_versions_is_left_out(coursework: TemplateVersion) -> None:
    scenario = Scenario(name={"ru": "Другая версия", "en": "Other"}, versions=("2025.*",))

    assert scenario_impacts(side_of(coursework), side_of(coursework), {"old": scenario}, TODAY) == ()


def test__impact__many_scenarios_are_all_calculated_and_summed(
    coursework: TemplateVersion, edited: TemplateVersion
) -> None:
    specs = input_specs(coursework)
    supervisor = next(s for s in specs if s.id == "supervisor")
    scenarios: dict[str, Scenario | str] = {}
    for index in range(200):
        value = supervisor.values[index % len(supervisor.values)]
        scenarios[f"s{index:03d}"] = Scenario(
            name={"ru": f"Сценарий {index}", "en": f"Scenario {index}"},
            inputs={"supervisor": value, "co_supervisor": "yes" if index % 2 else "no"},
        )

    started = time.perf_counter()
    impacts = scenario_impacts(side_of(coursework), side_of(edited), scenarios, TODAY)
    elapsed = time.perf_counter() - started

    body = impact_body(impacts, None)
    assert len(impacts) == 200
    assert body["summary"]["scenarios_total"] == 200
    # Меняются сценарии, где научрук из ВШЭ (академический руководитель появился в шаге 3).
    expected_changed = sum(
        1 for s in scenarios.values() if isinstance(s, Scenario) and s.inputs["supervisor"] == "university"
    )
    assert body["summary"]["scenarios_changed"] == expected_changed > 0
    assert body["summary"]["scenarios_changed"] + body["summary"]["scenarios_unchanged"] == 200
    assert elapsed < 30, elapsed
    assert len(json.dumps(body)) < 8 * 1024 * 1024


# ── Матрица ──────────────────────────────────────────────────────────────────


def test__matrix__starter_scenarios_match_their_expectations(coursework: TemplateVersion) -> None:
    rows = matrix_rows(side_of(coursework), scenarios_of(COURSEWORK), TODAY)

    # Строка на сценарий, которому версия подходит по `versions`; сценарии другой линии версий в матрицу не входят.
    assert [r.scenario for r in rows] == list(applicable_scenarios_of(COURSEWORK))
    assert rows
    for row in rows:
        assert row.status == "passed"
        assert [c.section for c in row.cells] == [
            "documents",
            "meta",
            "forms",
            "participants",
            "points",
            "route",
            "checks",
        ]
        by = {c.section: c for c in row.cells}
        assert all(by[s].status == "matched" for s in ("documents", "meta", "forms", "participants", "points", "route"))
        assert by["checks"].status == "unchecked"
        assert by["checks"].count > 0
        assert all(c.changed is None for c in row.cells)
    # Сценарии, которые не различают раздел, дают клеткам один отпечаток.
    by_supervisor = [r for r in rows if r.scenario in ("company-supervisor", "no-supervisor", "university-supervisor")]
    documents = {r.scenario: next(c for c in r.cells if c.section == "documents").fingerprint for r in by_supervisor}
    assert len(set(documents.values())) == 1
    routes = {r.scenario: next(c for c in r.cells if c.section == "route").fingerprint for r in by_supervisor}
    # Маршрут без научрука и с научруком из ВШЭ у курсового проекта один (шаг научрука остаётся: вопрос 1 дизайна).
    assert len(set(routes.values())) == 2
    assert routes["no-supervisor"] == routes["university-supervisor"] != routes["company-supervisor"]


def test__matrix__against_base_marks_the_edited_cells(coursework: TemplateVersion, edited: TemplateVersion) -> None:
    rows = {
        r.scenario: r for r in matrix_rows(side_of(edited), scenarios_of(COURSEWORK), TODAY, base=side_of(coursework))
    }

    cells = {s: {c.section: c for c in r.cells} for s, r in rows.items()}
    assert [c.section for c in rows["university-supervisor"].cells if c.changed] == ["route"]
    assert cells["university-supervisor"]["route"].status == "changed"
    assert cells["university-supervisor"]["documents"].changed is False
    assert not any(c.changed for c in rows["company-supervisor"].cells)
    # Снимок сценария записан до правки: утверждение про маршрут перестало выполняться, и это видно в итоге строки.
    assert rows["university-supervisor"].status == "failed"
    assert rows["company-supervisor"].status == "passed"


def test__matrix__error_unchecked_and_broken_files(coursework: TemplateVersion) -> None:
    plain = Scenario(name={"ru": "Без ожидания", "en": "No expectation"}, inputs={"supervisor": "company"})
    asserted = Scenario(
        name={"ru": "Одно утверждение", "en": "One assertion"},
        assertions=(DocumentStateAssertion(doc="report", state="active"),),
    )
    broken = Scenario(name={"ru": "Сломан", "en": "Broken"}, inputs={"kind": "nope"})
    scenarios: dict[str, Scenario | str] = {
        "asserted": asserted,
        "broken": broken,
        "file": "format: unreadable",
        "plain": plain,
    }

    rows = {r.scenario: r for r in matrix_rows(side_of(coursework), scenarios, TODAY)}

    assert rows["plain"].status == "unchecked"
    assert all(c.status == "unchecked" for c in rows["plain"].cells)
    assert rows["plain"].inputs["supervisor"] == "company"
    by = {c.section: c.status for c in rows["asserted"].cells}
    assert by["documents"] == "matched"
    assert {s for s, st in by.items() if st == "unchecked"} == {
        "meta",
        "forms",
        "participants",
        "points",
        "route",
        "checks",
    }
    for scenario_id in ("broken", "file"):
        row = rows[scenario_id]
        assert row.status == "error"
        assert row.message
        assert row.inputs == {}
        assert all((c.status, c.count, c.fingerprint) == ("error", 0, "") for c in row.cells)


def test__matrix__failed_assertion_marks_only_its_section(coursework: TemplateVersion) -> None:
    wrong = Scenario(
        name={"ru": "Неверное", "en": "Wrong"},
        assertions=(DocumentStateAssertion(doc="report", state="absent"),),
    )

    (row,) = matrix_rows(side_of(coursework), {"wrong": wrong}, TODAY)

    assert row.status == "failed"
    assert [(c.section, c.status) for c in row.cells if c.status != "unchecked"] == [("documents", "changed")]


# ── Контракт: тела проходят строгие модели и равны эталонам ───────────────────


def test__fixtures__equal_what_the_code_calculates(coursework: TemplateVersion, edited: TemplateVersion) -> None:
    bodies = cs.fixture_bodies(coursework, edited)

    for name, body in bodies.items():
        path = FIXTURES / f"{name}.json"
        assert json.loads(path.read_text(encoding="utf-8")) == json.loads(json.dumps(body)), name
    PackOutcomeCompareResponse.model_validate(bodies["PackOutcomeCompare/two_scenarios"])
    PackOutcomeImpactResponse.model_validate(bodies["PackOutcomeImpact/coursework"])
    PackOutcomeMatrixResponse.model_validate(bodies["PackOutcomeMatrix/coursework"])


def test__bodies__compare_and_matrix_builders_agree_with_the_models(coursework: TemplateVersion) -> None:
    example = example_of(coursework)
    scenarios = scenarios_of(COURSEWORK)
    comparison = compare_sides(
        Side(coursework, example, {}), Side(coursework, example, {"supervisor": "company"}), TODAY
    )
    header = {"workspace_id": cs.WORKSPACE, "pack": "hse-cs-sse", "template": "coursework", "version": "2026.1.6"}

    compare = PackOutcomeCompareResponse.model_validate({**header, **compare_body(comparison, "head", "base")})
    matrix = PackOutcomeMatrixResponse.model_validate(
        {**header, "state": "head", "revision": "r", **matrix_body(matrix_rows(side_of(coursework), scenarios, TODAY))}
    )

    assert (compare.left.state, compare.right.state) == ("head", "base")
    assert not compare.identical
    assert len(matrix.rows) == len(applicable_scenarios_of(COURSEWORK)) > 0


def test__resolve_side__includes_the_checks_section(coursework: TemplateVersion) -> None:
    outcome = resolve_side(Side(coursework, example_of(coursework), {}), TODAY)

    assert outcome.checks is not None
    assert any(rule.enabled for rule in outcome.checks)
