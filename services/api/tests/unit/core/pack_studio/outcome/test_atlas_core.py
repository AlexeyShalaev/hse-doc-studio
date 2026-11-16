"""Ядро атласа без вычислителя: ключ строки, сборка таблицы и групп исходов, влияние вводной, правила по трассе."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from hse_doc_studio.core.pack_studio.outcome.atlas import (
    SECTIONS,
    AtlasCancelled,
    AtlasTooLarge,
    ImpactAccumulator,
    Snapshot,
    assemble_table,
    combinations_count,
    encode_key,
    reading_rules,
    row_count,
)
from hse_doc_studio.core.pack_studio.outcome.model import Digest, ElementRef, Term
from hse_doc_studio.core.pack_studio.outcome.trace import Tracer, builtin_rule, manifest_rule

_DIGEST = Digest(documents={}, participants=(), meta_visible=(), points=(), sections=())


def _snapshot(
    fingerprint: str = "f", *, route: str = "r", elements: Mapping[str, int] | None = None, cosmetic: int = 0
) -> Snapshot:
    prints = tuple(route if section == "route" else "-" for section in SECTIONS)
    per_section = tuple(
        {("route_step", key): value for key, value in (elements or {}).items()} if s == "route" else {}
        for s in SECTIONS
    )
    return Snapshot(fingerprint, prints, per_section, cosmetic)


# ── Ключ ─────────────────────────────────────────────────────────────────────


def test__encode_key__joins_values_with_a_bar_and_escapes_a_bar_inside_a_value() -> None:
    assert encode_key(["university", "no", "yes"]) == "university|no|yes"
    assert encode_key(["a|b", "c"]) == "a%7Cb|c"
    assert encode_key([]) == ""
    assert encode_key(["Программиста и оператора", "x"]) == "Программиста и оператора|x"


def test__counts__are_products() -> None:
    assert row_count([("a", ["1", "2"]), ("b", ["1", "2", "3"])]) == 6
    assert row_count([]) == 1
    assert combinations_count([2, 3, 4]) == 24


# ── Таблица и группы ─────────────────────────────────────────────────────────


def _evaluate(combo: Mapping[str, str]) -> tuple[str, Digest]:
    # Исход зависит только от первого измерения: у второго значения дают один и тот же результат.
    return f"fp-{combo['a']}", _DIGEST


def test__assemble_table__groups_equal_outcomes_in_order_of_first_appearance() -> None:
    outcomes, rows = assemble_table([("a", ["x", "y"]), ("b", ["1", "2", "3"])], _evaluate)

    assert [(r.key, r.outcome) for r in rows] == [
        ("x|1", "o1"),
        ("x|2", "o1"),
        ("x|3", "o1"),
        ("y|1", "o2"),
        ("y|2", "o2"),
        ("y|3", "o2"),
    ]
    assert [(o.id, o.fingerprint, o.rows) for o in outcomes] == [("o1", "fp-x", 3), ("o2", "fp-y", 3)]


def test__assemble_table__without_dimensions_is_one_row_with_an_empty_key() -> None:
    outcomes, rows = assemble_table([], lambda _combo: ("fp", _DIGEST))

    assert [(r.key, r.outcome) for r in rows] == [("", "o1")]
    assert [o.rows for o in outcomes] == [1]


def test__assemble_table__a_table_over_the_limit_fails_before_any_row_is_evaluated() -> None:
    calls: list[object] = []

    def evaluate(combo: Mapping[str, str]) -> tuple[str, Digest]:
        calls.append(combo)
        return "fp", _DIGEST

    with pytest.raises(AtlasTooLarge) as caught:
        assemble_table([("a", ["1", "2", "3"]), ("b", ["1", "2", "3"])], evaluate, limit=8)

    assert (caught.value.rows, caught.value.limit) == (9, 8)
    assert calls == []


def test__assemble_table__the_limit_itself_is_allowed() -> None:
    _outcomes, rows = assemble_table([("a", ["1", "2"]), ("b", ["1", "2"])], _evaluate, limit=4)

    assert len(rows) == 4


def test__assemble_table__stops_when_the_caller_cancels() -> None:
    seen: list[int] = []

    def check() -> None:
        seen.append(1)
        if len(seen) == 3:
            raise AtlasCancelled

    with pytest.raises(AtlasCancelled):
        assemble_table([("a", ["1", "2", "3", "4"])], _evaluate, check=check)

    assert len(seen) == 3


# ── Влияние ──────────────────────────────────────────────────────────────────


def test__impact__a_changed_section_and_its_changed_elements_are_collected() -> None:
    acc = ImpactAccumulator("supervisor")
    left = _snapshot(route="r1", elements={"p/step/1": 1, "p/step/2": 2, "p/step/3": 3})
    right = _snapshot(route="r2", elements={"p/step/1": 1, "p/step/2": 9, "p/step/4": 4})

    acc.compare(left, right)
    impact = acc.result()

    assert impact.sections == ("route",)
    assert impact.elements == (
        ("route", "route_step", "p/step/2"),
        ("route", "route_step", "p/step/3"),
        ("route", "route_step", "p/step/4"),
    )
    assert impact.effective
    assert impact.ignored_reason is None


def test__impact__equal_prints_but_different_file_names_is_cosmetic() -> None:
    acc = ImpactAccumulator("lang")

    acc.compare(_snapshot(cosmetic=1), _snapshot(cosmetic=2))
    impact = acc.result()

    assert impact.sections == ()
    assert impact.cosmetic
    assert impact.ignored_reason == "cosmetic"


def test__impact__nothing_changed_is_no_effect() -> None:
    acc = ImpactAccumulator("kind")

    acc.compare(_snapshot(), _snapshot())
    acc.compare(_snapshot(), _snapshot())

    assert acc.result().ignored_reason == "no_effect"


def test__impact__a_structural_change_wins_over_a_cosmetic_one() -> None:
    acc = ImpactAccumulator("staffing")

    acc.compare(_snapshot(route="r1", cosmetic=1), _snapshot(route="r2", cosmetic=2))
    impact = acc.result()

    assert impact.sections == ("route",)
    assert not impact.cosmetic
    assert impact.ignored_reason is None


# ── Правила, которые читают вводную ──────────────────────────────────────────


def test__reading_rules__lists_each_rule_once_and_sees_parts_of_an_input() -> None:
    tracer = Tracer()
    slot = manifest_rule("version.yaml", "/pack_submission/profiles/0/signing_slots/1/when")
    gate = builtin_rule("nda_gate")
    for rule, term, element in (
        (slot, Term("equals", "supervisor.role", ("company",)), "a"),
        (slot, Term("equals", "supervisor.role", ("company",)), "b"),
        (gate, Term("truthy", "nda"), "c"),
    ):
        tracer.decide(
            rule=rule,
            kind="slot_when",
            effect="gate",
            terms=[term],
            actual={},
            status="held",
            subjects=[ElementRef("route", element)],
        )

    trace = tracer.entries()

    assert reading_rules(trace, "supervisor") == [slot]
    assert reading_rules(trace, "nda") == [gate]
    assert reading_rules(trace, "co_supervisor") == []
    assert reading_rules(trace, "super") == []
