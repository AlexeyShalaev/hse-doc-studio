"""Пак с пресетом маршрута для юнит-тестов (docs/design/signing-route.md, 15.10): `hse-cs-sse` 2026.1.3 с ключами
2026.1.5 по таблице 15.10 поверх, точка «Заявка на тему КП» и проект с людьми."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from hse_doc_studio.core.catalog import (
    SignatureDefaultDate,
    SignatureDefaultPlacement,
    SigningSlotPreset,
    SlotCondition,
    SubmissionProfile,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import DateMarkFormat, PersonRole, ProjectKind, ProjectStaffing
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.value_objects import Author, Person
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.projects.create_project import _build_documents
from hse_doc_studio.use_cases.signing_route.point import RoutePoint, build_point

from tests.factories import make_project

PACKS = Path(__file__).resolve().parents[6] / "packs"
TOPIC = "topic-approval"
PROPOSAL = "project_proposal"
APPLICATION = "topic_application"

PROPOSAL_PLACE = SignatureDefaultPlacement(page=1, x_mm=80, y_mm=139, width_mm=40)
APPLICATION_PLACE = SignatureDefaultPlacement(page=1, x_mm=163, y_mm=168, width_mm=40)
AUTHOR_PLACE = SignatureDefaultPlacement(page=1, x_mm=165, y_mm=200, width_mm=30)
PROPOSAL_DATES = (
    SignatureDefaultDate(page=1, x_mm=81, y_mm=156, width_mm=7, height_mm=5, format=DateMarkFormat.day),
    SignatureDefaultDate(page=1, x_mm=90, y_mm=156, width_mm=24, height_mm=5, format=DateMarkFormat.month_word),
)
CONSULTANT_WHEN = SlotCondition(person="co_supervisor")
ACADEMIC_WHEN = SlotCondition(person="supervisor", role=PersonRole.company)

_templates = YamlTemplateRepository(PACKS)


def released(version_id: str = "2026.1.3") -> TemplateVersion:
    """`hse-cs-sse/coursework` как выпущен: 2026.1.3 и 2026.1.4 без пресетов."""
    found = _templates.get_version("hse-cs-sse", "coursework", version_id)
    assert found is not None
    return found


def preset_version(*, signing_slots: tuple[SigningSlotPreset, ...] | None = None) -> TemplateVersion:
    """2026.1.3 с пресетом по таблице 15.10: места по документам, метки даты научрука на «Описании проекта»,
    консультант и академрук на «Заявлении» по условию."""
    base = released()
    slots = []
    for slot in base.signatures_config.slots:
        if slot.id == "supervisor":
            slot = replace(
                slot,
                placements=((PROPOSAL, PROPOSAL_PLACE), (APPLICATION, APPLICATION_PLACE)),
                default_dates=((PROPOSAL, PROPOSAL_DATES),),
            )
        elif slot.id == "author":
            slot = replace(slot, placements=((APPLICATION, AUTHOR_PLACE),))
        slots.append(slot)
    entries = (
        signing_slots
        if signing_slots is not None
        else (
            SigningSlotPreset(doc_id=APPLICATION, slot_id="co_supervisor", when=CONSULTANT_WHEN),
            SigningSlotPreset(doc_id=APPLICATION, slot_id="academic_supervisor", when=ACADEMIC_WHEN),
        )
    )
    profiles = tuple(replace(p, signing_slots=entries) if p.id == TOPIC else p for p in base.pack_submission.profiles)
    return replace(
        base,
        version="2026.1.90",
        signatures_config=replace(base.signatures_config, slots=tuple(slots)),
        pack_submission=replace(base.pack_submission, profiles=profiles),
    )


def profile(version: TemplateVersion, profile_id: str = TOPIC) -> SubmissionProfile:
    return next(p for p in version.pack_submission.profiles if p.id == profile_id)


def project(
    version: TemplateVersion,
    *,
    supervisor: PersonRole | None = PersonRole.university,
    consultant: bool = False,
) -> Project:
    docs = _build_documents(
        version, None, ProjectStaffing.solo, [Author(name="Иванов Иван")], shared_enabled=True, kind=ProjectKind.project
    )
    base = make_project(documents=docs)
    return replace(
        base,
        lock=replace(base.lock, pack_id="hse-cs-sse", template_id="coursework", version=version.version),
        kind=ProjectKind.project,
        supervisor=Person(name="Петров Пётр", role=supervisor) if supervisor is not None else None,
        co_supervisor=Person(name="Сидоров Сидор", role=PersonRole.company) if consultant else None,
    )


def point(version: TemplateVersion, proj: Project, profile_id: str = TOPIC) -> RoutePoint:
    return build_point(proj, version, profile(version, profile_id), ProjectTemplateService())
