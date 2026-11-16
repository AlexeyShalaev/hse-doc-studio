"""Матрица «сценарии на разделы»: клетка, её отпечаток, счётчик и статус (раздел 3.6 и 4.5 дизайна результата, O7).

Чистые функции над готовым `Outcome` (проверки посчитаны) и сценарием. Клетка раздела:

- `fingerprint` и `count`: отпечаток структуры раздела и число его элементов (документов в комплекте, видимых полей,
  применимых анкет, участников, активных пунктов, пар маршрута, включённых правил проверок). Клетки с одним отпечатком
  у разных сценариев показывают, что сценарии раздел не различают;
- `status`: `matched` ожидание сценария по разделу (снимок или утверждение) выполнено, `changed` не выполнено или
  (при сравнении с базой) раздел отличается от базы, `unchecked` ожидания у раздела нет, `error` результата нет
  (вводные не подходят к версии);
- `changed`: отличается ли отпечаток раздела от базы; None, если с базой не сравнивали или сценария на базе нет.

Утверждение относится к разделу по виду: документы (`document_state`, `document_count`), метаданные (`meta_visible`),
участники (`participant_present`), пункты (`item_active`), маршрут (`route_steps`, `route_pair`). Снимок покрывает все
разделы, кроме проверок (их в снимке нет).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from hse_doc_studio.core.pack_studio.outcome.model import SECTIONS, Digest, Outcome, SectionName
from hse_doc_studio.core.pack_studio.outcome.scenario_check import check_assertions
from hse_doc_studio.core.pack_studio.outcome.scenarios import Scenario
from hse_doc_studio.core.pack_studio.outcome.summary import checks_print

type CellStatus = Literal["matched", "changed", "unchecked", "error"]

_ASSERTION_SECTION: dict[str, SectionName] = {
    "document_state": "documents",
    "document_count": "documents",
    "meta_visible": "meta",
    "participant_present": "participants",
    "item_active": "points",
    "route_steps": "route",
    "route_pair": "route",
}
# Снимок сценария записан без проверок: их отпечаток в нём пустой.
_NOT_IN_SNAPSHOT: frozenset[SectionName] = frozenset({"checks"})


@dataclass(frozen=True, slots=True)
class CellPrint:
    section: SectionName
    fingerprint: str
    count: int


def cell_prints(outcome: Outcome) -> tuple[CellPrint, ...]:
    """Отпечатки и счётчики клеток по разделам; `checks` берётся из применимости правил, если она посчитана."""
    by_section = {p.section: p for p in outcome.digest.sections}
    prints: list[CellPrint] = []
    for section in SECTIONS:
        if section == "checks":
            fingerprint, count = checks_print(outcome)
            prints.append(CellPrint(section, fingerprint, count))
        else:
            found = by_section[section]
            prints.append(CellPrint(section, found.fingerprint, found.count))
    return tuple(prints)


def _snapshot_sections(snapshot: Digest, outcome: Outcome) -> tuple[set[SectionName], set[SectionName]]:
    """Разделы, которые покрывает снимок, и те из них, где результат от него отличается."""
    now = {p.section: p for p in outcome.digest.sections}
    covered: set[SectionName] = set()
    failing: set[SectionName] = set()
    for old in snapshot.sections:
        if old.section in _NOT_IN_SNAPSHOT:
            continue
        covered.add(old.section)
        current = now.get(old.section)
        if current is None or (current.fingerprint, current.count) != (old.fingerprint, old.count):
            failing.add(old.section)
    return covered, failing


def _assertion_sections(scenario: Scenario, outcome: Outcome) -> tuple[set[SectionName], set[SectionName]]:
    """Разделы, которые покрывают утверждения, и те из них, где утверждение не выполнено."""
    failed = {failure.index for failure in check_assertions(outcome, scenario.assertions)}
    covered = {_ASSERTION_SECTION[a.kind] for a in scenario.assertions}
    failing = {_ASSERTION_SECTION[a.kind] for i, a in enumerate(scenario.assertions) if i in failed}
    return covered, failing


def expectation_statuses(scenario: Scenario | None, outcome: Outcome) -> dict[SectionName, CellStatus]:
    """Статус клетки по ожиданию сценария: `matched`, `changed` (не выполнено) или `unchecked` (ожидания нет)."""
    if scenario is None or not scenario.has_expectation:
        return dict.fromkeys(SECTIONS, "unchecked")
    covered, failing = _assertion_sections(scenario, outcome)
    if scenario.snapshot is not None:
        snap_covered, snap_failing = _snapshot_sections(scenario.snapshot, outcome)
        covered |= snap_covered
        failing |= snap_failing
    return {s: "unchecked" if s not in covered else "changed" if s in failing else "matched" for s in SECTIONS}


def against_base(
    current: Mapping[SectionName, CellPrint], base: Mapping[SectionName, CellPrint]
) -> dict[SectionName, bool]:
    """Какие разделы отличаются от базы (по отпечатку; счётчик следует за отпечатком)."""
    return {s: current[s].fingerprint != base[s].fingerprint for s in SECTIONS}


__all__ = ["CellPrint", "CellStatus", "against_base", "cell_prints", "expectation_statuses"]
