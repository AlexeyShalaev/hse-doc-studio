"""Раздел результата «участники»: авторы проекта и три руководителя (бледный слот, если человека нет)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from hse_doc_studio.core.pack_studio.outcome.facts import PERSONAS
from hse_doc_studio.core.pack_studio.outcome.model import ParticipantOutcome, RoutePerson
from hse_doc_studio.core.signing_route.preset import project_person

if TYPE_CHECKING:
    from hse_doc_studio.core.entities import Project

AUTHOR_PERSONA = "author"
type Role = Literal["author", "supervisor", "co_supervisor", "academic_supervisor"]


def author_persona(project: Project, index: int) -> str:
    """Персона автора: слаг в команде (`author1`, `author2`), `author` в одиночной работе (R11 дизайна)."""
    author = project.authors[index]
    return author.slug or AUTHOR_PERSONA


def evaluate_participants(project: Project) -> tuple[ParticipantOutcome, ...]:
    participants = [
        ParticipantOutcome(
            persona=author_persona(project, index),
            role="author",
            name=author.name,
            present=True,
            org=None,
        )
        for index, author in enumerate(project.authors)
    ]
    for persona in PERSONAS:
        person = project_person(project, persona)
        participants.append(
            ParticipantOutcome(
                persona=persona,
                role=persona,  # type: ignore[arg-type]
                name=person.name if person is not None else "",
                present=person is not None,
                org=person.role.value if person is not None else None,
            )
        )
    return tuple(participants)


def steps_without_person(
    steps: tuple[tuple[RoutePerson, ...], ...], participants: tuple[ParticipantOutcome, ...]
) -> tuple[tuple[int, str], ...]:
    """Шаги маршрута, которые ждут человека, которого нет в комбинации: пары «номер шага с 1, персона».

    При `supervisor: none` шаг `[supervisor]` остаётся в маршруте (так считает движок), а в нём человек с пустым
    именем. Результат это не прячет: экран и линтер по этим парам показывают предупреждение «нет человека для шага»."""
    present = {p.persona for p in participants if p.present}
    return tuple(
        (number, person.persona)
        for number, step in enumerate(steps, start=1)
        for person in step
        if person.persona not in present
    )
