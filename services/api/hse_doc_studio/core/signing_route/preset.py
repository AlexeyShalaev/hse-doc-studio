"""Пресет маршрута точки из пака: состав, условия и сравнение с маршрутом (docs/design/signing-route.md, 15.3-15.6).

Пресет читается вживую из версии шаблона проекта, как порядок 5.2: шаги из персон (`default_route` с парами сверх
точки), слоты сверх точки, условия которых выполнены на людях проекта (`when`), отметки `optional` пар и слоты,
которые шаблон не добавил по условию. В файлах проекта лежит только результат применения (места, метки даты,
отметки `optional`), а маршрут хранит свой состав. Сравнение маршрута с пресетом (`differs`) считается при чтении и
ничего не пишет.

Модуль чистый: пары пресета на документы и рантайм-слоты проекта раскладывает сценарий (`use_cases/signing_route/
preset.py`), здесь типы, условия и сравнение.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.catalog import SlotCondition
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.signing_route.drafting import PersonDraft
from hse_doc_studio.core.signing_route.entities import DocSlot, Participant, SigningRoute
from hse_doc_studio.core.value_objects import Person

type Steps = tuple[tuple[str, ...], ...]


class PresetDiff(StrEnum):
    """Чем маршрут отличается от пресета точки (`SigningRoute.preset.differs`, 15.11)."""

    order = "order"  # шаги и люди по персонам
    slots = "slots"  # слоты сверх точки
    optional = "optional"  # отметки «Подпись необязательна» у пар маршрута


@dataclass(frozen=True)
class PresetSlot:
    """Пара сверх точки из пресета и её условие (None: шаблон добавляет её всегда)."""

    pair: DocSlot
    when: SlotCondition | None = None


@dataclass(frozen=True)
class RoutePreset:
    """Пресет точки для проекта сейчас: на текущих людях проекта и его документах.

    `extra_slots` пары сверх точки, которые шаблон добавляет (условие выполнено или его нет); `skipped_by_condition`
    пары сверх точки, которые шаблон не добавил, потому что условие не выполнено; `optional` пары точки и включённые
    пары сверх точки, которые шаблон отмечает необязательными.
    """

    version: str
    steps: Steps
    extra_slots: tuple[PresetSlot, ...] = ()
    optional: tuple[DocSlot, ...] = ()
    skipped_by_condition: tuple[PresetSlot, ...] = ()

    @property
    def extra_pairs(self) -> tuple[DocSlot, ...]:
        return tuple(item.pair for item in self.extra_slots)

    def adds(self, pair: DocSlot) -> bool:
        """Шаблон сам добавляет эту пару сверх точки."""
        return pair in self.extra_pairs

    def marks_optional(self, pair: DocSlot) -> bool:
        return pair in self.optional


def project_person(project: Project, persona: str) -> Person | None:
    """Человек проекта на персоне руководителя (`PERSON_KEYS`); None, если его нет или имя пустое."""
    person = {
        "supervisor": project.supervisor,
        "co_supervisor": project.co_supervisor,
        "academic_supervisor": project.academic_supervisor,
    }.get(persona)
    if person is None or not (person.name or "").strip():
        return None
    return person


def condition_met(when: SlotCondition | None, project: Project) -> bool:
    """Условие пресета на людях проекта: человек указан и, если задана роль, у него эта роль (15.3)."""
    if when is None:
        return True
    person = project_person(project, when.person)
    if person is None:
        return False
    return when.role is None or person.role == when.role


def route_steps(route: SigningRoute) -> Steps:
    """Шаги маршрута персонами по порядку; внутри шага по алфавиту (параллельный шаг порядка не имеет)."""
    return tuple(tuple(sorted(p.persona for p in route.participants if p.step == number)) for number in route.steps)


def _canonical(steps: Steps) -> Steps:
    return tuple(tuple(sorted(step)) for step in steps if step)


def route_extras(route: SigningRoute, point_pairs: Collection[DocSlot]) -> frozenset[DocSlot]:
    """Пары маршрута сверх точки: все назначенные пары, которых точка не требует."""
    return frozenset(pair for pair in route.pairs if pair not in point_pairs)


def preset_differs(
    preset: RoutePreset,
    route: SigningRoute,
    point_pairs: Collection[DocSlot],
    marked_optional: Collection[DocSlot],
) -> tuple[PresetDiff, ...]:
    """Чем состав маршрута отличается от пресета; пусто: маршрут как в шаблоне.

    `point_pairs` пары, которые требует точка; `marked_optional` пары с отметкой «Подпись необязательна» на точке
    маршрута. Отметки сравниваются только у пар маршрута (пары точки и его пары сверх точки).
    """
    found: list[PresetDiff] = []
    if route_steps(route) != _canonical(preset.steps):
        found.append(PresetDiff.order)
    if route_extras(route, point_pairs) != frozenset(preset.extra_pairs):
        found.append(PresetDiff.slots)
    pairs = {*point_pairs, *route.pairs}
    marked = {pair for pair in marked_optional if pair in pairs}
    wanted = {pair for pair in preset.optional if pair in pairs}
    if marked != wanted:
        found.append(PresetDiff.optional)
    return tuple(found)


def preset_people(
    participants: Sequence[Participant], steps: Iterable[Iterable[str]]
) -> tuple[tuple[PersonDraft, ...], ...]:
    """Шаги пресета людьми маршрута для `apply_people` («Вернуть как в шаблоне», 15.6).

    Участник с персоной шага остаётся (по `id`, со своим человеком и согласием) на её новом шаге; на персону берётся
    первый ещё не занятый участник с ней. Персона без участника получает нового человека «нет в проекте», которого
    затем подбирает `resolve_unassigned`. Участники, чьей персоны в пресете нет, и повторы персоны выпадают.
    """
    used: set[object] = set()
    result: list[tuple[PersonDraft, ...]] = []
    for step in steps:
        drafts: list[PersonDraft] = []
        for persona in step:
            found = next((p for p in participants if p.persona == persona and p.id not in used), None)
            if found is None:
                drafts.append(PersonDraft(persona=persona))
                continue
            used.add(found.id)
            drafts.append(
                PersonDraft(persona=persona, id=found.id, user_id=found.user_id, invitation_id=found.invitation_id)
            )
        if drafts:
            result.append(tuple(drafts))
    return tuple(result)
