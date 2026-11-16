"""Сравнение двух результатов: что изменилось по разделам и элементам, и почему (раздел 4.5 дизайна результата, O7).

Чистые функции над готовыми `Outcome` (с трассой): ни файлов, ни часов, ни вычислителя. Какие результаты сравнивать
(два набора вводных, два сценария, одна комбинация на двух состояниях версии), решает вызывающий.

- **Изменения** (`diff_outcomes`) берутся из индекса элементов (`summary.outcome_elements`), то есть из структуры, а не
  из косметики: имена файлов, языковая редакция, доступность вариантов и значения примера в них не попадают (R12), как
  и в отпечаток. Поэтому равные отпечатки это отсутствие изменений. Знак: `+` элемент появился (документ вошёл в
  комплект, пункт стал активен, поле стало видимым, шаг или пара добавлены), `-` исчез, `~` остался, но изменился
  (шаг маршрута с другими людьми, у пары другой источник, у пункта другие подписи).
- **Причины** (`why` у изменения) это правила трассы, из-за которых так вышло: решения элемента (`why` результата)
  слева и справа, у которых отличается исход или фактические значения. Если различий нет (элемент изменился из-за
  соседа, например шаг маршрута из-за появившегося человека), берётся цепочка стороны, где элемент есть.
- **Проверки** (`checks`) участвуют, только если они посчитаны у обоих результатов (`include`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import replace
from typing import Any

from hse_doc_studio.core.pack_studio.outcome.explain import ElementInfo, ElementKey, element_infos
from hse_doc_studio.core.pack_studio.outcome.model import (
    SECTIONS,
    ChangeReason,
    Outcome,
    SectionDelta,
    SectionName,
    TraceEntry,
)
from hse_doc_studio.core.pack_studio.outcome.scenario_check import Change, ChangeSymbol
from hse_doc_studio.core.pack_studio.outcome.summary import Element, outcome_elements

# Сколько причин держит одно изменение (остальные отбрасываются: самые важные идут первыми).
MAX_REASONS = 6

# Виды, у которых элемент либо есть, либо нет (знак `+` или `-` по появлению).
_PRESENCE = frozenset({"point", "participant", "route_step", "route_pair", "skipped_pair"})
# Виды, у которых показаны значения даже у появившегося и исчезнувшего (для остальных они `None`).
_VALUED = frozenset({"document", "route_step", "route_pair", "may_add"})


def _flag(kind: str, structure: Any) -> bool:
    """Включён ли элемент вида «флаг»: документ в комплекте, поле видимо, пункт активен, правило применимо."""
    if kind == "document":
        return bool(structure) and structure[0] == "active"
    return bool(structure) and bool(structure[0])


def _join(items: Iterable[Any]) -> str:
    return ", ".join(str(item) for item in items if item is not None)


def _text(kind: str, structure: Any) -> str | None:  # noqa: PLR0911, C901 — по виду элемента
    """Значение элемента для «было» и «стало»: одной строкой, по-английски как значения вводных и состояния."""
    if structure is None:
        return None
    if kind == "document":
        state, owners = structure
        listed = _join(owners)
        return f"{state} [{listed}]" if listed else str(state)
    if kind == "meta_field":
        visible, required_at = structure
        return f"{'visible' if visible else 'hidden'}, required_at={required_at}"
    if kind == "form":
        applies, per_author = structure
        return f"applies={_bool(applies)}, per_author={_bool(per_author)}"
    if kind == "form_field":
        visible, required = structure
        return f"{'visible' if visible else 'hidden'}, required={_bool(required)}"
    if kind == "participant":
        return str(structure)
    if kind == "item":
        active, reason, signatures = structure
        return f"{'active' if active else 'off'}{f' ({reason})' if reason else ''}{_signatures(signatures)}"
    if kind == "extra_item":
        active, reason = structure
        return f"{'active' if active else 'off'}{f' ({reason})' if reason else ''}"
    if kind == "route_step":
        return _join(structure)
    if kind == "route_pair":
        persona, source, optional = structure
        return f"{persona} ({source}{', optional' if optional else ''})"
    if kind == "may_add":
        return _join(f"{doc}/{slot}" for doc, slot in structure)
    if kind == "check_rule":
        enabled, reason, applies_to = structure
        return f"{'enabled' if enabled else 'off'}{f' ({reason})' if reason else ''} [{_join(applies_to)}]"
    return None


def _bool(value: object) -> str:
    return "true" if value else "false"


def _signatures(signatures: Iterable[str]) -> str:
    listed = _join(signatures)
    return f" [{listed}]" if listed else ""


_PLAIN_LABELS = {
    "document": "документ",
    "meta_field": "поле",
    "form": "анкета",
    "form_field": "поле анкеты",
    "participant": "участник",
    "point": "точка",
    "check_rule": "правило проверки",
}


def _label(kind: str, element_id: str) -> str:
    """Подпись для человека; по виду и id, как у изменений снимка (`документ`, `участник`, `поле`, `точка`)."""
    if kind in _PLAIN_LABELS:
        return f"{_PLAIN_LABELS[kind]} {element_id}"
    head, _, rest = element_id.partition("/")
    if kind == "item":
        return f"{head}: пункт {rest}"
    if kind == "extra_item":
        return f"{head}: дополнительный файл {rest}"
    if kind == "route_step":
        return f"{head}: шаг {rest.removeprefix('step/')}"
    if kind == "may_add":
        return f"{element_id}: подписи, которые автор включит сам"
    parts = rest.split("/")
    who = parts[2] if len(parts) > 2 else parts[-1]  # noqa: PLR2004 — документ, слот и необязательная персона
    suffix = ", условие не выполнено" if kind == "skipped_pair" else ""
    return f"{head}: {parts[0]}: {who}{suffix}"


def _change(
    kind: str, section: SectionName, element_id: str, left: Element | None, right: Element | None
) -> Change | None:
    """Изменение одного элемента между сторонами; None, если структура та же."""
    old, new = (left.structure if left else None), (right.structure if right else None)
    if left is not None and right is not None and old == new:
        return None
    if left is None and right is None:
        return None
    if kind == "may_add" and (old or []) == (new or []):
        return None
    if kind in _PRESENCE:
        symbol: ChangeSymbol = "+" if left is None else "-" if right is None else "~"
    elif kind == "may_add":
        symbol = "~"
    else:
        was, now = left is not None and _flag(kind, old), right is not None and _flag(kind, new)
        symbol = "+" if now and not was else "-" if was and not now else "~"
    shown = symbol == "~" or kind in _VALUED
    before = _text(kind, old) if shown else None
    after = _text(kind, new) if shown else None
    if kind == "may_add":
        before, after = _text(kind, old or []), _text(kind, new or [])
    return Change(symbol, section, kind, element_id, _label(kind, element_id), before, after)


def _identity(entry: TraceEntry) -> tuple[object, ...]:
    """Правило как одно и то же с обеих сторон: место в манифесте и вид; условие правка могла изменить, тогда причина
    одна, с условием «после» и исходами «до» и «после»."""
    return (entry.rule, entry.kind)


def _chain(info: ElementInfo | None, trace: Mapping[str, TraceEntry]) -> dict[tuple[object, ...], TraceEntry]:
    entries = (trace[i] for i in (info.why if info else ()) if i in trace)
    return {_identity(e): e for e in entries}


def _reason(left: TraceEntry | None, right: TraceEntry | None) -> ChangeReason:
    entry = right or left
    assert entry is not None  # noqa: S101 — вызывается только для существующей стороны
    return ChangeReason(
        rule=entry.rule,
        kind=entry.kind,
        terms=entry.terms,
        before=left.status if left else None,
        after=right.status if right else None,
        before_actual=dict(left.actual) if left else {},
        after_actual=dict(right.actual) if right else {},
    )


def _reasons(
    change: Change,
    before: Mapping[ElementKey, ElementInfo],
    after: Mapping[ElementKey, ElementInfo],
    before_trace: Mapping[str, TraceEntry],
    after_trace: Mapping[str, TraceEntry],
) -> tuple[ChangeReason, ...]:
    key = (change.section, change.id)
    left, right = _chain(before.get(key), before_trace), _chain(after.get(key), after_trace)
    differing: list[ChangeReason] = []
    for identity in dict.fromkeys([*left, *right]):
        was, now = left.get(identity), right.get(identity)
        if was is None or now is None or (was.status, was.actual, was.terms) != (now.status, now.actual, now.terms):
            differing.append(_reason(was, now))
    if differing:
        return tuple(differing[:MAX_REASONS])
    # Правила те же с обеих сторон: причина в соседях элемента; показана цепочка стороны, где он есть.
    side = left if change.symbol == "-" else right or left
    return tuple(_reason(left.get(i), right.get(i)) for i in side)[:MAX_REASONS]


def diff_outcomes(before: Outcome, after: Outcome, *, reasons: bool = True) -> tuple[Change, ...]:
    """Изменения от `before` к `after` по разделам в порядке результата. `reasons=False` не собирает причины (они
    нужны, только когда у обоих результатов есть трасса)."""
    old, new = outcome_elements(before), outcome_elements(after)
    both_checks = before.checks is not None and after.checks is not None
    infos = (
        element_infos(before),
        element_infos(after),
        {t.id: t for t in before.trace},
        {t.id: t for t in after.trace},
    )
    changes: list[Change] = []
    for section in SECTIONS:
        if section == "checks" and not both_checks:
            continue
        left = {(e.kind, e.id): e for e in old[section]}
        right = {(e.kind, e.id): e for e in new[section]}
        for kind, element_id in dict.fromkeys([*left, *right]):
            change = _change(kind, section, element_id, left.get((kind, element_id)), right.get((kind, element_id)))
            if change is None:
                continue
            if reasons:
                change = replace(change, why=_reasons(change, *infos))
            changes.append(change)
    return tuple(changes)


def section_deltas(changes: Iterable[Change]) -> tuple[SectionDelta, ...]:
    """Сводка изменений по разделам: добавлено, изменено, убрано. Пустые разделы в сводку не входят."""
    counts: dict[SectionName, list[int]] = {}
    for change in changes:
        row = counts.setdefault(change.section, [0, 0, 0])
        row[{"+": 0, "~": 1, "-": 2}[change.symbol]] += 1
    return tuple(SectionDelta(section, *counts[section]) for section in SECTIONS if section in counts)


__all__ = ["MAX_REASONS", "diff_outcomes", "section_deltas"]
