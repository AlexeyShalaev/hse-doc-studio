"""Факты о версии и синтетическом проекте: срез, из которого вычислители читают условия (раздел 4.1 дизайна)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from hse_doc_studio.core.pack_studio.outcome.inputs import answers_of, nda_input_id, variants_of
from hse_doc_studio.core.pack_studio.outcome.predicates import STAFFING_SOLO, STAFFING_TEAM, nda_enabled
from hse_doc_studio.core.pack_studio.preview import NO, SWITCH_KIND, SWITCH_LANG, SWITCH_STAFFING, YES
from hse_doc_studio.core.signing_route.preset import project_person

if TYPE_CHECKING:
    from hse_doc_studio.core.catalog import TemplateVersion
    from hse_doc_studio.core.entities import Project

PERSONAS: tuple[str, ...] = ("supervisor", "co_supervisor", "academic_supervisor")


def yes_no(value: bool) -> str:
    return YES if value else NO


@dataclass(frozen=True, slots=True)
class Facts:
    """Неизменяемый срез фактов: вводные запроса и то, что из них вышло в синтетическом проекте."""

    inputs: Mapping[str, str]
    kind: str
    lang: str
    # Значение вводной `staffing` (`solo`, `team2`, `team3`) и режим состава документов (`solo` или `team`).
    staffing: str
    staffing_mode: str
    nda: bool
    # Id вводной NDA (`nda` или `meta.nda`): под этим именем условие стоит в трассе.
    nda_subject: str
    manuals: str
    answers: Mapping[str, Mapping[str, Any]]
    variants: Mapping[str, str]
    # Персона руководителя -> роль человека (`university` или `company`); нет в словаре: человека нет.
    people: Mapping[str, str]

    def has_person(self, persona: str) -> bool:
        return persona in self.people

    def person_role(self, persona: str) -> str | None:
        return self.people.get(persona)


def facts_of(version: TemplateVersion, project: Project, inputs: Mapping[str, str]) -> Facts:
    people = {
        persona: str(person.role) for persona in PERSONAS if (person := project_person(project, persona)) is not None
    }
    staffing = inputs.get(SWITCH_STAFFING, STAFFING_SOLO)
    return Facts(
        inputs=dict(inputs),
        kind=inputs.get(SWITCH_KIND) or str(project.kind),
        lang=inputs.get(SWITCH_LANG) or str(project.lang),
        staffing=staffing,
        staffing_mode=STAFFING_SOLO if staffing == STAFFING_SOLO else STAFFING_TEAM,
        nda=nda_enabled(project.meta),
        nda_subject=nda_input_id(version),
        manuals=str(project.meta.get("manuals") or ""),
        answers=answers_of(version, inputs),
        variants=variants_of(version, inputs),
        people=people,
    )
