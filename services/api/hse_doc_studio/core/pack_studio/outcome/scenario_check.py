"""Проверка результата по ожиданию сценария: утверждения, сравнение со снимком, статус и покрытие правил.

Чистые функции над готовым результатом (`Outcome`): ни файлов, ни часов. Прогон (расчёт результата по вводным
сценария) делает `use_cases/pack_studio/outcome/scenario_runner.py`, здесь только вердикт.

Статусы (дизайн результата, 5.3): `passed`, `failed` (есть расхождение), `error` (вводные не подходят к версии,
результата нет) и `unchecked` (нет ни снимка, ни утверждений). Расхождение со снимком показывается списком изменений
`+`, `~`, `-` по `digest` (документы, участники, видимые поля, пункты, шаги маршрута, число пар); если отпечаток
раздела изменился, а `digest` объяснить не может (изменилась обязательность поля, порядок), раздел попадает в список
одной строкой с отпечатками.
"""

from __future__ import annotations

import json
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Literal

from hse_doc_studio.core.pack_studio.outcome.coverage import Coverage, RuleCoverage, coverage_of
from hse_doc_studio.core.pack_studio.outcome.model import (
    Digest,
    DigestPoint,
    Outcome,
    PointOutcome,
    SectionName,
    SectionPrint,
)
from hse_doc_studio.core.pack_studio.outcome.points import step_id
from hse_doc_studio.core.pack_studio.outcome.scenarios import (
    Assertion,
    DocumentCountAssertion,
    DocumentStateAssertion,
    ItemActiveAssertion,
    MetaVisibleAssertion,
    ParticipantAssertion,
    RoutePairAssertion,
    RouteStepsAssertion,
    Scenario,
)
from hse_doc_studio.core.pack_studio.outcome.summary import fingerprint_of

type StatusName = Literal["passed", "failed", "error", "unchecked"]
type ChangeSymbol = Literal["+", "~", "-"]

MAX_WHY = 16

# Раздел, у которого отпечаток изменился без объяснимых изменений: вид элемента для строки списка.
_SECTION_KIND = {
    "documents": "document",
    "meta": "meta_field",
    "forms": "form",
    "participants": "participant",
    "points": "point",
    "route": "route_step",
    "checks": "check_rule",
}


@dataclass(frozen=True, slots=True)
class Failure:
    """Расхождение с ожиданием (`ScenarioFailure` контракта). `index` утверждения, у снимка `None`; `why` это решения
    трассы результата, из-за которых получилось то, что получилось."""

    index: int | None
    kind: str
    expected: str
    actual: str
    why: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Change:
    """Одно изменение результата относительно снимка (`OutcomeChange` контракта)."""

    symbol: ChangeSymbol
    section: SectionName
    kind: str
    id: str
    label: str
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class Verdict:
    status: StatusName
    failures: tuple[Failure, ...] = ()
    changes: tuple[Change, ...] = ()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _norm(steps: Iterable[Iterable[str]]) -> list[list[str]]:
    """Шаги маршрута без учёта порядка внутри шага."""
    return [sorted(step) for step in steps]


def _point(outcome: Outcome, point_id: str) -> PointOutcome | None:
    return next((p for p in outcome.points if p.id == point_id), None)


# ── Утверждения ──────────────────────────────────────────────────────────────


def check_assertions(outcome: Outcome, assertions: Iterable[Assertion]) -> tuple[Failure, ...]:
    failures: list[Failure] = []
    for index, assertion in enumerate(assertions):
        failure = _check(outcome, index, assertion)
        if failure is not None:
            failures.append(failure)
    return tuple(failures)


def _check(outcome: Outcome, index: int, assertion: Assertion) -> Failure | None:
    if isinstance(assertion, DocumentStateAssertion):
        return _check_document(outcome, index, assertion)
    if isinstance(assertion, DocumentCountAssertion):
        count = sum(1 for d in outcome.documents if d.state == assertion.state)
        return _verdict(index, assertion, str(assertion.count), str(count), ())
    if isinstance(assertion, MetaVisibleAssertion):
        meta = next((m for m in outcome.meta if m.id == assertion.field), None)
        visible = meta is not None and meta.visible
        return _verdict(index, assertion, _flag(assertion.visible), _flag(visible), meta.why if meta else ())
    if isinstance(assertion, ParticipantAssertion):
        person = next((p for p in outcome.participants if p.persona == assertion.persona), None)
        present = person is not None and person.present
        return _verdict(index, assertion, _flag(assertion.present), _flag(present), person.why if person else ())
    return _check_route(outcome, index, assertion)


def _check_document(outcome: Outcome, index: int, assertion: DocumentStateAssertion) -> Failure | None:
    doc = next((d for d in outcome.documents if d.id == assertion.doc), None)
    actual = doc.state if doc is not None else "missing"
    return _verdict(index, assertion, assertion.state, actual, doc.why if doc is not None else ())


def _check_route(outcome: Outcome, index: int, assertion: Assertion) -> Failure | None:
    if isinstance(assertion, ItemActiveAssertion):
        return _check_item(outcome, index, assertion)
    if isinstance(assertion, RouteStepsAssertion):
        return _check_steps(outcome, index, assertion)
    if isinstance(assertion, RoutePairAssertion):
        return _check_pair(outcome, index, assertion)
    return None


def _verdict(index: int, assertion: Assertion, expected: str, actual: str, why: Iterable[str]) -> Failure | None:
    if expected == actual:
        return None
    return Failure(index, assertion.kind, expected, actual, tuple(why)[:MAX_WHY])


def _check_item(outcome: Outcome, index: int, assertion: ItemActiveAssertion) -> Failure | None:
    point = _point(outcome, assertion.point)
    if point is None:
        return Failure(index, assertion.kind, _flag(assertion.active), "missing point", ())
    item = next((i for i in point.items if i.doc_id == assertion.doc), None)
    active = item is not None and item.active
    return _verdict(index, assertion, _flag(assertion.active), _flag(active), item.why if item is not None else ())


def _check_steps(outcome: Outcome, index: int, assertion: RouteStepsAssertion) -> Failure | None:
    point = _point(outcome, assertion.point)
    if point is None:
        return Failure(index, assertion.kind, _json([list(s) for s in assertion.steps]), "missing point", ())
    steps = [[p.persona for p in step] for step in point.route.steps]
    if _norm(steps) == _norm(assertion.steps):
        return None
    return Failure(
        index, assertion.kind, _json([list(s) for s in assertion.steps]), _json(steps), point.route.why[:MAX_WHY]
    )


def _check_pair(outcome: Outcome, index: int, assertion: RoutePairAssertion) -> Failure | None:
    point = _point(outcome, assertion.point)
    if point is None:
        return Failure(index, assertion.kind, _flag(assertion.present), "missing point", ())
    pairs = [
        pair
        for pair in point.route.pairs
        if (pair.doc_id, pair.slot_id, pair.persona) == (assertion.doc, assertion.slot, assertion.persona)
    ]
    why = pairs[0].why if pairs else _skipped_why(point, assertion) or point.route.why
    return _verdict(index, assertion, _flag(assertion.present), _flag(bool(pairs)), why)


def _skipped_why(point: PointOutcome, assertion: RoutePairAssertion) -> tuple[str, ...]:
    """Почему пары нет: решения пропущенной пары (условие `when` не выполнено), если такая есть; иначе пары нет
    просто потому, что слот не назван в подписях пункта, и причина это маршрут точки."""
    skipped = next(
        (s for s in point.route.skipped if (s.doc_id, s.slot_id) == (assertion.doc, assertion.slot)),
        None,
    )
    return skipped.why if skipped is not None else ()


# ── Снимок ───────────────────────────────────────────────────────────────────


def snapshot_fingerprint(snapshot: Digest) -> str:
    """Отпечаток результата, из которого записан снимок (по отпечаткам разделов); пусто у снимка без разделов."""
    return fingerprint_of(snapshot.sections) if snapshot.sections else ""


def diff_digest(snapshot: Digest, current: Digest) -> tuple[Change, ...]:
    """Что изменилось от снимка к текущему результату: `+` появилось, `-` исчезло, `~` изменилось."""
    changes: list[Change] = []
    changes.extend(_documents(snapshot, current))
    changes.extend(_names("participants", "participant", "участник", snapshot.participants, current.participants))
    changes.extend(_names("meta", "meta_field", "поле", snapshot.meta_visible, current.meta_visible))
    changes.extend(_points(snapshot, current))
    changes.extend(_unexplained_sections(snapshot, current, changes))
    return tuple(changes)


def _documents(snapshot: Digest, current: Digest) -> list[Change]:
    changes: list[Change] = []
    for doc_id in [*snapshot.documents, *(d for d in current.documents if d not in snapshot.documents)]:
        before, after = snapshot.documents.get(doc_id), current.documents.get(doc_id)
        if before == after:
            continue
        # В комплекте документ только в состоянии active: `inactive` и `absent` для проекта то же, что «нет».
        symbol: ChangeSymbol = "+" if after == "active" else "-" if before == "active" else "~"
        changes.append(Change(symbol, "documents", "document", doc_id, f"документ {doc_id}", before, after))
    return changes


def _names(
    section: SectionName, kind: str, label: str, before: Collection[str], after: Collection[str]
) -> list[Change]:
    changes = [Change("-", section, kind, name, f"{label} {name}", name, None) for name in before if name not in after]
    changes.extend(
        Change("+", section, kind, name, f"{label} {name}", None, name) for name in after if name not in before
    )
    return changes


def _points(snapshot: Digest, current: Digest) -> list[Change]:
    old = {p.id: p for p in snapshot.points}
    new = {p.id: p for p in current.points}
    changes: list[Change] = []
    for point_id in [*old, *(i for i in new if i not in old)]:
        before, after = old.get(point_id), new.get(point_id)
        if before is None or after is None:
            symbol: ChangeSymbol = "+" if before is None else "-"
            changes.append(Change(symbol, "points", "point", point_id, f"точка {point_id}", None, None))
            continue
        changes.extend(_point_changes(before, after))
    return changes


def _point_changes(before: DigestPoint, after: DigestPoint) -> list[Change]:
    point_id = before.id
    changes = [
        Change("-", "points", "item", f"{point_id}/{doc}", f"{point_id}: пункт {doc}", doc, None)
        for doc in before.items
        if doc not in after.items
    ]
    changes.extend(
        Change("+", "points", "item", f"{point_id}/{doc}", f"{point_id}: пункт {doc}", None, doc)
        for doc in after.items
        if doc not in before.items
    )
    for number in range(1, max(len(before.steps), len(after.steps)) + 1):
        left = before.steps[number - 1] if number <= len(before.steps) else None
        right = after.steps[number - 1] if number <= len(after.steps) else None
        if left is not None and right is not None and sorted(left) == sorted(right):
            continue
        symbol: ChangeSymbol = "+" if left is None else "-" if right is None else "~"
        changes.append(
            Change(
                symbol,
                "route",
                "route_step",
                step_id(point_id, number),
                f"{point_id}: шаг {number}",
                ", ".join(left) if left is not None else None,
                ", ".join(right) if right is not None else None,
            )
        )
    if before.pairs != after.pairs:
        changes.append(
            Change(
                "~",
                "route",
                "route_pair",
                f"{point_id}/pairs",
                f"{point_id}: пар подписи",
                str(before.pairs),
                str(after.pairs),
            )
        )
    return changes


def _unexplained_sections(snapshot: Digest, current: Digest, explained: Iterable[Change]) -> list[Change]:
    """Разделы, у которых отпечаток или счётчик другой, а изменений в них выше нет: одной строкой на раздел."""
    covered = {change.section for change in explained}
    now = {p.section: p for p in current.sections}
    changes: list[Change] = []
    for old in snapshot.sections:
        new: SectionPrint | None = now.get(old.section)
        if new is None or (new.fingerprint, new.count) == (old.fingerprint, old.count) or old.section in covered:
            continue
        changes.append(
            Change(
                "~",
                old.section,
                _SECTION_KIND[old.section],
                old.section,
                f"раздел {old.section}: структура изменилась",
                old.fingerprint,
                new.fingerprint,
            )
        )
    return changes


def _change_why(outcome: Outcome, change: Change) -> tuple[str, ...]:
    """Решения трассы по элементу, который ещё есть в результате (у исчезнувшего их нет)."""
    if change.symbol == "-" and change.kind not in {"item", "route_step"}:
        return ()
    if change.kind == "document":
        return next((d.why for d in outcome.documents if d.id == change.id), ())
    if change.kind == "participant":
        return next((p.why for p in outcome.participants if p.persona == change.id), ())
    if change.kind == "meta_field":
        return next((m.why for m in outcome.meta if m.id == change.id), ())
    point = _point(outcome, change.id.split("/", 1)[0])
    return _point_why(point, change) if point is not None else ()


def _point_why(point: PointOutcome, change: Change) -> tuple[str, ...]:
    if change.kind == "item":
        doc = change.id.split("/", 1)[1]
        return next((i.why for i in point.items if i.doc_id == doc), ())
    if change.kind in {"route_step", "route_pair"}:
        return point.route.why
    return point.why


def _unique(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))[:MAX_WHY]


# ── Вердикт ──────────────────────────────────────────────────────────────────


def judge(scenario: Scenario, outcome: Outcome) -> Verdict:
    """Результат сценария по его ожиданию. Утверждения и снимок независимы: упасть могут оба."""
    if not scenario.has_expectation:
        return Verdict("unchecked")
    failures = list(check_assertions(outcome, scenario.assertions))
    changes: tuple[Change, ...] = ()
    if scenario.snapshot is not None:
        changes = diff_digest(scenario.snapshot, outcome.digest)
        if changes:
            why = _unique(w for change in changes for w in _change_why(outcome, change))
            failures.append(
                Failure(None, "snapshot", snapshot_fingerprint(scenario.snapshot), outcome.fingerprint, why)
            )
    return Verdict("failed" if failures else "passed", tuple(failures), changes)


__all__ = [
    "Change",
    "Coverage",
    "Failure",
    "RuleCoverage",
    "StatusName",
    "Verdict",
    "check_assertions",
    "coverage_of",
    "diff_digest",
    "judge",
    "snapshot_fingerprint",
]
