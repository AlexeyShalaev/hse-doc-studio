"""Сводка результата: индекс элементов, отпечатки разделов, `digest` и разница по разделам (ветки).

Отпечаток считается по структуре: состояние документов, видимость и обязательность полей, пункты, шаги и пары
маршрута, применимость проверок. Косметика в него не входит (R12 дизайна): имена файлов, языковая редакция,
доступность и выбор варианта, имена и организации людей, значения примера. Так вводная `lang` у результата ничего не
меняет, а атлас не множит исходы без пользы. Точное имя файла и подобное даёт сам результат, а не отпечаток.

Индекс элементов (`outcome_elements`) один для отпечатков, веток и будущих сравнений: у элемента вид, id по контракту
(документ `id`, поле `id`, поле анкеты `<анкета>/<поле>`, участник `persona`, точка `id`, пункт `<точка>/<документ>`,
шаг `<точка>/step/<номер>`, пара `<точка>/<документ>/<слот>`), структура и косметика.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hse_doc_studio.core.pack_studio.outcome.model import (
    SECTIONS,
    Digest,
    DigestPoint,
    SectionDelta,
    SectionName,
    SectionPrint,
)
from hse_doc_studio.core.pack_studio.outcome.points import pair_id, step_id

if TYPE_CHECKING:
    from hse_doc_studio.core.pack_studio.outcome.model import Outcome


@dataclass(frozen=True, slots=True)
class Element:
    """Элемент результата для сравнения: что в нём структура (меняет отпечаток), что косметика."""

    section: SectionName
    kind: str
    id: str
    structure: Any
    cosmetic: Any = None


def _hash(value: Any, length: int) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def _documents(outcome: Outcome) -> list[Element]:
    return [
        Element(
            "documents",
            "document",
            doc.id,
            [doc.state, [inst.owner for inst in doc.instances]],
            [
                doc.lang_state,
                doc.source_file,
                [(v.id, v.available, v.chosen) for v in doc.variants],
                [inst.file_name for inst in doc.instances],
            ],
        )
        for doc in outcome.documents
    ]


def _meta(outcome: Outcome) -> list[Element]:
    return [
        Element("meta", "meta_field", field.id, [field.visible, field.required_at], field.value)
        for field in outcome.meta
    ]


def _forms(outcome: Outcome) -> list[Element]:
    elements: list[Element] = []
    for form in outcome.forms:
        elements.append(Element("forms", "form", form.id, [form.applies, form.per_author]))
        elements.extend(
            Element("forms", "form_field", f"{form.id}/{f.id}", [f.visible, f.required]) for f in form.fields
        )
    return elements


def _participants(outcome: Outcome) -> list[Element]:
    return [
        Element("participants", "participant", person.persona, person.role, [person.name, person.org])
        for person in outcome.participants
        if person.present
    ]


def _points(outcome: Outcome) -> list[Element]:
    elements: list[Element] = []
    for point in outcome.points:
        elements.append(Element("points", "point", point.id, []))
        elements.extend(
            Element(
                "points", "item", f"{point.id}/{item.doc_id}", [item.active, item.off_reason, list(item.signatures)]
            )
            for item in point.items
        )
        elements.extend(
            Element("points", "extra_item", f"{point.id}/{extra.source}", [extra.active, extra.off_reason])
            for extra in point.extra_items
        )
    return elements


def _route(outcome: Outcome) -> list[Element]:
    elements: list[Element] = []
    for point in outcome.points:
        route = point.route
        elements.extend(
            Element("route", "route_step", step_id(point.id, number), [p.persona for p in step], [p.name for p in step])
            for number, step in enumerate(route.steps, start=1)
        )
        elements.extend(
            Element(
                "route",
                "route_pair",
                pair_id(point.id, pair.doc_id, pair.slot_id, pair.persona),
                [pair.persona, pair.source, pair.optional],
            )
            for pair in route.pairs
        )
        elements.extend(
            Element("route", "skipped_pair", f"{point.id}/{skip.doc_id}/{skip.slot_id}", []) for skip in route.skipped
        )
        # Подписи, которые автор включит сам, отдельным элементом точки: они часть структуры маршрута.
        elements.append(Element("route", "may_add", point.id, sorted([s.doc_id, s.slot_id] for s in route.may_add)))
    return elements


def _checks(outcome: Outcome) -> list[Element]:
    return [
        Element("checks", "check_rule", rule.id, [rule.enabled, rule.off_reason, list(rule.applies_to)])
        for rule in outcome.checks or ()
    ]


def outcome_elements(outcome: Outcome) -> dict[SectionName, list[Element]]:
    """Все элементы результата по разделам, в порядке результата."""
    return {
        "documents": _documents(outcome),
        "meta": _meta(outcome),
        "forms": _forms(outcome),
        "participants": _participants(outcome),
        "points": _points(outcome),
        "route": _route(outcome),
        "checks": _checks(outcome),
    }


def section_print(section: SectionName, elements: list[Element]) -> str:
    """Отпечаток раздела: 12 знаков от структуры его элементов."""
    return _hash([[e.kind, e.id, e.structure] for e in elements], 12)


def _counts(outcome: Outcome) -> dict[SectionName, int]:
    return {
        "documents": sum(1 for d in outcome.documents if d.state == "active"),
        "meta": sum(1 for f in outcome.meta if f.visible),
        "forms": sum(1 for f in outcome.forms if f.applies),
        "participants": sum(1 for p in outcome.participants if p.present),
        "points": sum(1 for pt in outcome.points for i in pt.items if i.active),
        "route": sum(len(pt.route.pairs) for pt in outcome.points),
        "checks": sum(1 for c in outcome.checks or () if c.enabled),
    }


def section_prints(outcome: Outcome) -> tuple[SectionPrint, ...]:
    """Отпечатки и счётчики разделов. Проверки в них не входят (отпечаток и `digest` не зависят от `include`): раздел
    `checks` всегда пуст, правила проверок читают из `outcome.checks`."""
    elements = outcome_elements(outcome)
    elements["checks"] = []
    counts = {**_counts(outcome), "checks": 0}
    return tuple(SectionPrint(s, section_print(s, elements[s]), counts[s]) for s in SECTIONS)


def fingerprint_of(prints: tuple[SectionPrint, ...]) -> str:
    """Отпечаток всей структуры результата без трассы: 16 знаков от отпечатков разделов."""
    return _hash([[p.section, p.fingerprint] for p in prints], 16)


def digest_of(outcome: Outcome, prints: tuple[SectionPrint, ...]) -> Digest:
    """Сжатый результат: хватает, чтобы мгновенно перерисовать экран из атласа и записать снимок в сценарий."""
    return Digest(
        documents={doc.id: doc.state for doc in outcome.documents},
        participants=tuple(p.persona for p in outcome.participants if p.present),
        meta_visible=tuple(f.id for f in outcome.meta if f.visible),
        points=tuple(
            DigestPoint(
                id=point.id,
                items=tuple(i.doc_id for i in point.items if i.active),
                steps=tuple(tuple(p.persona for p in step) for step in point.route.steps),
                pairs=len(point.route.pairs),
            )
            for point in outcome.points
        ),
        sections=prints,
    )


def diff_sections(before: Outcome, after: Outcome) -> tuple[SectionDelta, ...]:
    """Что изменится по разделам при переходе от `before` к `after`: элементов добавлено, изменено и убрано.

    `may_add` в счёт не идёт (это пометка точки, а не элемент); пустые разделы в ответ не попадают."""
    old, new = outcome_elements(before), outcome_elements(after)
    deltas: list[SectionDelta] = []
    for section in SECTIONS:
        left = {(e.kind, e.id): e.structure for e in old[section] if e.kind != "may_add"}
        right = {(e.kind, e.id): e.structure for e in new[section] if e.kind != "may_add"}
        added = sum(1 for key in right if key not in left)
        removed = sum(1 for key in left if key not in right)
        changed = sum(1 for key, value in right.items() if key in left and left[key] != value)
        if added or removed or changed:
            deltas.append(SectionDelta(section, added, changed, removed))
    return tuple(deltas)
