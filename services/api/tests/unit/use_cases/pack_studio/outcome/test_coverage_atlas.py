"""Покрытие правил сценариями по строкам атласа (срез O8, раздел 6.2): достижимые исходы, процент, строки, подсказки.

Курсовой проект `hse-cs-sse` 2026.1.6 (12 строк атласа) и ВКР `hse-cs-se` 2026.1.2 (864 строки)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from hse_doc_studio.core.pack_studio.outcome.atlas import encode_key
from hse_doc_studio.core.pack_studio.outcome.coverage import (
    MAX_UNCOVERED_ROWS,
    RuleUniverse,
    coverage_of,
    outcomes_universe,
)
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio.outcome.lint import scan_atlas
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.outcome.scenario_runner import atlas_universe, coverage_universe

TODAY = date(2026, 11, 16)
_PACKS = Path(__file__).resolve().parents[7] / "packs"


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(_PACKS)


@pytest.fixture(scope="module")
def course(repo: YamlTemplateRepository):  # type: ignore[no-untyped-def]
    version = repo.get_version("hse-cs-sse", "coursework", "2026.1.6")
    assert version is not None
    example = auto_examples(version)[0]
    return version, example, scan_atlas(version, example, TODAY).universe


def _outcome(course, **inputs: str):  # type: ignore[no-untyped-def]
    version, example, _ = course
    return resolve(version, inputs, example, TODAY)


def test__universe__rules_are_the_ones_with_a_reachable_outcome_and_every_row_has_cells(course) -> None:  # type: ignore[no-untyped-def]
    _, _, universe = course

    assert len(universe.rows) == 12 == len(universe.row_cells)
    assert universe.dimensions == ("supervisor", "co_supervisor", "academic_supervisor")
    assert all(rule.possible and set(rule.possible) <= {"held", "not_held"} for rule in universe.rules)
    assert all(set(rule.witness) == set(rule.possible) for rule in universe.rules)
    # Правило, у которого достижим один исход (условие всегда выполнено), не требует второго.
    assert any(len(rule.possible) == 1 for rule in universe.rules)
    assert any(len(rule.possible) == 2 for rule in universe.rules)


def test__universe__includes_every_rule_the_old_approximation_saw(repo: YamlTemplateRepository) -> None:
    version = repo.get_version("hse-cs-se", "vkr", "2026.1.2")
    assert version is not None
    example = auto_examples(version)[0]

    atlas = {r.rule for r in scan_atlas(version, example, TODAY).universe.rules}
    old = {r.rule for r in outcomes_universe(coverage_universe(version, auto_examples(version), TODAY)).rules}

    assert old <= atlas


def test__coverage__nothing_seen_means_every_rule_uncovered_and_zero_percent(course) -> None:  # type: ignore[no-untyped-def]
    _, _, universe = course

    cover = coverage_of(universe, {})

    assert cover.rules_covered == cover.rules_half == 0
    assert cover.rules_uncovered == cover.rules_total == len(universe.rules)
    assert cover.percent == 0.0
    assert (cover.rows_total, cover.rows_touched) == (12, 0)
    assert not cover.approximate


def test__coverage__a_scenario_on_a_row_touches_it_and_raises_the_percent(course) -> None:  # type: ignore[no-untyped-def]
    _, _, universe = course
    one = _outcome(course, supervisor="company", co_supervisor="yes", academic_supervisor="yes")
    two = _outcome(course, supervisor="none", co_supervisor="no", academic_supervisor="no")

    first = coverage_of(universe, {"a": one})
    both = coverage_of(universe, {"a": one, "b": two})

    assert first.rows_touched == 1
    assert both.rows_touched == 2
    assert 0 < first.percent < both.percent <= 100
    assert both.rules_covered > first.rules_covered
    assert first.scenarios == 1
    assert coverage_of(universe, {"a": one}, total=5).scenarios == 5
    assert first.rules_covered + first.rules_half + first.rules_uncovered == first.rules_total


def test__coverage__a_rule_with_one_reachable_outcome_is_covered_by_seeing_it(course) -> None:  # type: ignore[no-untyped-def]
    _, _, universe = course
    cover = coverage_of(universe, {"a": _outcome(course)})

    always = {r.rule for r in universe.rules if len(r.possible) == 1}
    partial = {r.rule for r in cover.rules}
    seen = {e.rule for e in _outcome(course).trace if e.status != "skipped"}

    assert not (always & seen & partial)


def test__coverage__partial_rules_name_the_row_that_closes_the_gap(course) -> None:  # type: ignore[no-untyped-def]
    version, example, universe = course
    cover = coverage_of(universe, {"a": _outcome(course)})
    by_rule = {r.rule: r for r in universe.rules}

    gaps = [r for r in cover.rules if r.seen != r.possible]
    assert gaps
    for item in gaps:
        missing = next(s for s in item.possible if s not in item.seen)
        assert item.witness == by_rule[item.rule].witness[missing]
        # По этой строке правило действительно получает недостающий исход.
        replay = resolve(version, item.witness, example, TODAY)
        assert any(e.rule == item.rule and e.status == missing for e in replay.trace)


def test__coverage__uncovered_rows_are_greedy_limited_and_close_the_gaps(course) -> None:  # type: ignore[no-untyped-def]
    _, _, universe = course
    cover = coverage_of(universe, {})

    rows = cover.uncovered_rows
    assert 0 < len(rows) <= MAX_UNCOVERED_ROWS
    assert [r.gain for r in rows] == sorted((r.gain for r in rows), reverse=True)
    assert rows[0].gain >= rows[-1].gain >= 1
    assert set(rows[0].inputs) == set(universe.dimensions)


def test__coverage__rules_list_is_limited_and_counts_the_omitted(course) -> None:  # type: ignore[no-untyped-def]
    _, _, universe = course

    cover = coverage_of(universe, {}, limit=3)

    assert len(cover.rules) == 3
    assert cover.rules_omitted == len(universe.rules) - 3


def test__coverage__scenario_off_the_atlas_dimensions_still_lands_on_a_row_by_its_dimension_values(course) -> None:  # type: ignore[no-untyped-def]
    _, _, universe = course
    outcome = _outcome(course, supervisor="company")

    key = encode_key(outcome.inputs[d] for d in universe.dimensions)

    assert key in universe.row_keys
    assert coverage_of(universe, {"a": outcome}).rows_touched == 1


def test__coverage__old_style_universe_of_outcomes_is_marked_approximate(course) -> None:  # type: ignore[no-untyped-def]
    version, example, _ = course

    cover = coverage_of(coverage_universe(version, auto_examples(version), TODAY), {"a": _outcome(course)})

    assert cover.approximate
    assert cover.uncovered_rows == ()
    assert cover.rows_total == 0


def test__atlas_universe__scenario_run_uses_the_atlas_rows(repo: YamlTemplateRepository) -> None:
    version = repo.get_version("hse-cs-sse", "coursework", "2026.1.6")
    assert version is not None

    universe = atlas_universe(version, auto_examples(version), TODAY)

    assert isinstance(universe, RuleUniverse)
    assert len(universe.rows) == 12
    assert universe.from_atlas
