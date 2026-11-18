"""Покрытие правил сценариями по строкам атласа (раздел 6.2 дизайна результата, срез O8).

Покрытие отвечает на вопрос «какие правила пака и какие комбинации вводных проверяют мои сценарии». Универсум это
строки атласа (`RuleUniverse`): результат каждой строки считается с трассой, и по ней видно, какие исходы правил
вообще достижимы (`possible`: `held`, `not_held`; `skipped` не считается) и в какой строке каждый исход виден
(`witness`). Раньше универсум строился по умолчаниям и переключению вводных по одной, и правило, видное только при
сочетании двух вводных, в него не попадало.

Правило покрыто полностью, если сценарии видели все его достижимые исходы, наполовину, если часть, не покрыто, если
ни одного. Правило, у которого в атласе достижим один исход (условие, которое всегда выполнено), покрыто полностью
после первого сценария, который его видел: второго исхода не существует, и считать его пробелом нельзя (его отдельно
называет правило `when-always-held`). Процент покрытия это доля увиденных достижимых исходов правил.

Комбинации: строка атласа затронута сценарием, если вводные сценария на измерениях атласа совпали с ключом строки.
`uncovered_rows` это до `MAX_UNCOVERED_ROWS` строк, которые закрывают больше всего ещё не увиденных исходов правил
(жадный выбор по данным атласа; подсказка «Добавить сценарии» клиента берёт их или считает сама).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from hse_doc_studio.core.pack_studio.outcome.atlas import encode_key
from hse_doc_studio.core.pack_studio.outcome.model import Outcome, RuleRef

type Seen = Literal["held", "not_held"]
type Witness = dict[str, str]

OUTCOMES: tuple[Seen, ...] = ("held", "not_held")
# Правил в ответе не больше этого (остальные посчитаны, но не перечислены: `rules_omitted`), строк-подсказок тоже.
MAX_COVERAGE_RULES = 200
MAX_UNCOVERED_ROWS = 10
MAX_COVERAGE_SCENARIOS = 64


@dataclass(frozen=True, slots=True)
class UniverseRule:
    """Правило универсума: какие исходы достижимы в атласе и в какой строке виден каждый."""

    rule: RuleRef
    kind: str
    possible: tuple[Seen, ...]
    witness: Mapping[str, Witness]


@dataclass(frozen=True, slots=True)
class RuleUniverse:
    """Правила и строки атласа. `rows` значения измерений по порядку `dimensions`; `row_cells` у каждой строки
    множество «правило, исход» (номер правила на два плюс 0 у `held` и 1 у `not_held`)."""

    rules: tuple[UniverseRule, ...] = ()
    dimensions: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = ()
    row_cells: tuple[frozenset[int], ...] = ()
    # Универсум не из атласа (замена на `outcomes_universe`): строк нет, комбинации не считаются.
    from_atlas: bool = True

    @property
    def row_keys(self) -> frozenset[str]:
        return frozenset(encode_key(values) for values in self.rows)

    def row_inputs(self, index: int) -> Witness:
        return dict(zip(self.dimensions, self.rows[index], strict=True))


@dataclass(frozen=True, slots=True)
class RuleCoverage:
    rule: RuleRef
    kind: str
    # Исходы, которые видели сценарии, и исходы, достижимые в атласе.
    seen: tuple[Seen, ...]
    possible: tuple[Seen, ...]
    scenarios: tuple[str, ...]
    # Строка атласа, где виден первый недостающий исход; None: в атласе её нет (универсум не из атласа).
    witness: Witness | None = None


@dataclass(frozen=True, slots=True)
class UncoveredRow:
    """Строка атласа, которую стоит закрыть сценарием: значения измерений и сколько исходов правил она добавит."""

    inputs: Witness
    gain: int


@dataclass(frozen=True, slots=True)
class Coverage:
    """Покрытие правил манифеста сценариями. `rules` только покрытые не полностью, не больше `MAX_COVERAGE_RULES`."""

    scenarios: int
    rules_total: int
    rules_covered: int
    rules_half: int
    rules_uncovered: int
    rules: tuple[RuleCoverage, ...]
    percent: float = 0.0
    rows_total: int = 0
    rows_touched: int = 0
    uncovered_rows: tuple[UncoveredRow, ...] = ()
    rules_omitted: int = 0
    # Атлас не построен (слишком большой): универсум приближённый, цифры нижняя граница.
    approximate: bool = False


def outcomes_universe(outcomes: Iterable[Outcome]) -> RuleUniverse:
    """Универсум из результатов с трассой (приближение без атласа): правила и исходы, которые видны в этих
    результатах. Комбинации не считаются."""
    kinds: dict[RuleRef, str] = {}
    seen: dict[RuleRef, dict[str, None]] = {}
    for outcome in outcomes:
        for entry in outcome.trace:
            kinds.setdefault(entry.rule, entry.kind)
            found = seen.setdefault(entry.rule, {})
            if entry.status != "skipped":
                found.setdefault(entry.status)
    rules = tuple(
        UniverseRule(rule, kinds[rule], tuple(s for s in OUTCOMES if s in found), {})
        for rule, found in seen.items()
        if found
    )
    return RuleUniverse(rules=rules, from_atlas=False)


def _scenario_seen(seen_by: Mapping[str, Outcome]) -> tuple[dict[RuleRef, set[str]], dict[RuleRef, list[str]]]:
    outcomes: dict[RuleRef, set[str]] = {}
    owners: dict[RuleRef, list[str]] = {}
    for scenario_id, outcome in seen_by.items():
        for entry in outcome.trace:
            if entry.status == "skipped":
                continue
            outcomes.setdefault(entry.rule, set()).add(entry.status)
            owner = owners.setdefault(entry.rule, [])
            if scenario_id not in owner:
                owner.append(scenario_id)
    return outcomes, owners


def _rule_coverage(
    rule: UniverseRule, seen: set[str], owners: Sequence[str]
) -> tuple[Literal["full", "half", "none"], RuleCoverage]:
    possible = set(rule.possible)
    got = tuple(s for s in OUTCOMES if s in seen and s in possible)
    missing = [s for s in rule.possible if s not in seen]
    state: Literal["full", "half", "none"] = "full" if not missing else "half" if got else "none"
    witness = dict(rule.witness[missing[0]]) if missing and missing[0] in rule.witness else None
    return state, RuleCoverage(rule.rule, rule.kind, got, rule.possible, tuple(owners), witness)


def _touched_rows(universe: RuleUniverse, seen_by: Mapping[str, Outcome]) -> int:
    if not universe.rows:
        return 0
    keys = universe.row_keys
    touched = {encode_key(outcome.inputs.get(dim, "") for dim in universe.dimensions) for outcome in seen_by.values()}
    return len(touched & keys)


def _greedy_rows(universe: RuleUniverse, wanted: set[int], limit: int) -> tuple[UncoveredRow, ...]:
    """Строки, которые по очереди закрывают больше всего недостающих исходов (жадный выбор)."""
    picked: list[UncoveredRow] = []
    remaining = set(wanted)
    while remaining and len(picked) < limit:
        best, gain = -1, 0
        for index, cells in enumerate(universe.row_cells):
            count = len(cells & remaining)
            if count > gain:
                best, gain = index, count
        if best < 0:
            break
        picked.append(UncoveredRow(universe.row_inputs(best), gain))
        remaining -= universe.row_cells[best]
    return tuple(picked)


def coverage_of(  # noqa: PLR0914 — универсум, сценарии и итоги одного расчёта
    universe: RuleUniverse | Iterable[Outcome],
    seen_by: Mapping[str, Outcome],
    *,
    total: int | None = None,
    limit: int = MAX_COVERAGE_RULES,
) -> Coverage:
    """Покрытие правил результатами сценариев (`seen_by` по id; у сценариев с ошибкой результата нет). `universe` это
    `RuleUniverse` по строкам атласа либо результаты с трассой (приближение). `total` число всех сценариев."""
    base = universe if isinstance(universe, RuleUniverse) else outcomes_universe(universe)
    got, owners = _scenario_seen(seen_by)
    rules = list(base.rules)
    known = {item.rule for item in rules}
    # Правило, которое видел сценарий, а атлас нет (другой набор данных), попадает в универсум с тем, что видели.
    for outcome in seen_by.values():
        for entry in outcome.trace:
            if entry.rule not in known and got.get(entry.rule):
                known.add(entry.rule)
                rules.append(
                    UniverseRule(entry.rule, entry.kind, tuple(s for s in OUTCOMES if s in got[entry.rule]), {})
                )
    counts = {"full": 0, "half": 0, "none": 0}
    partial: list[tuple[str, RuleCoverage]] = []
    seen_pairs = possible_pairs = 0
    for item in rules:
        state, cover = _rule_coverage(item, got.get(item.rule, set()), owners.get(item.rule, ()))
        counts[state] += 1
        seen_pairs += len(cover.seen)
        possible_pairs += len(cover.possible)
        if state != "full":
            partial.append((state, cover))
    partial.sort(key=lambda pair: pair[0] != "none")
    wanted = {
        index * 2 + OUTCOMES.index(status)
        for index, item in enumerate(base.rules)
        for status in item.possible
        if status not in got.get(item.rule, set())
    }
    percent = round(100 * seen_pairs / possible_pairs, 1) if possible_pairs else 100.0
    return Coverage(
        scenarios=len(seen_by) if total is None else total,
        rules_total=len(rules),
        rules_covered=counts["full"],
        rules_half=counts["half"],
        rules_uncovered=counts["none"],
        rules=tuple(cover for _, cover in partial[:limit]),
        percent=percent,
        rows_total=len(base.rows),
        rows_touched=_touched_rows(base, seen_by),
        uncovered_rows=_greedy_rows(base, wanted, MAX_UNCOVERED_ROWS) if base.from_atlas else (),
        rules_omitted=max(0, len(partial) - limit),
        approximate=not base.from_atlas,
    )
