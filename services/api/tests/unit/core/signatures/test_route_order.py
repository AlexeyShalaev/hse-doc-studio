"""Порядок маршрута подписания по умолчанию: из пака, иначе встроенный (docs/design/signing-route.md, раздел 5.2)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import (
    PackSubmissionConfig,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    SubmissionDocItem,
    SubmissionProfile,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ProjectKind, ProjectStaffing
from hse_doc_studio.core.signatures.route_order import BUILTIN_ROUTE, default_route, route_order
from hse_doc_studio.core.value_objects import Author
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.projects.create_project import _build_documents

from tests.factories import make_document_definition, make_project, make_template_version

_PACKS = Path(__file__).resolve().parents[6] / "packs"
_TEAM = [
    Author(name="Шалаев Алексей", slug="shalaev", managed=True),
    Author(name="Иванов Иван", slug="ivanov", managed=True),
]


def _slot(slot_id: str, applies_to: tuple[str, ...] = ("app",), *, per_author: bool = False) -> SignatureSlotDef:
    return SignatureSlotDef(
        id=slot_id,
        label={"ru": slot_id},
        applies_to=applies_to,
        default_placement=SignatureDefaultPlacement(page=1, x_mm=10, y_mm=10, width_mm=40),
        per_author=per_author,
    )


def _profile(signatures: tuple[str, ...], route: tuple[tuple[str, ...], ...] = ()) -> SubmissionProfile:
    return SubmissionProfile(
        id="topic",
        name={"ru": "Заявка"},
        description={"ru": ""},
        items=(SubmissionDocItem(doc_id="app", signatures=signatures),),
        extra_items=(),
        signing_route=route,
    )


_SSE_SLOTS = (
    _slot("author", per_author=True),
    _slot("supervisor"),
    _slot("co_supervisor"),
    _slot("academic_supervisor"),
)


def _version(
    slots: tuple[SignatureSlotDef, ...] = _SSE_SLOTS,
    route: tuple[tuple[str, ...], ...] = (),
    profile: SubmissionProfile | None = None,
) -> TemplateVersion:
    return replace(
        make_template_version(documents=(make_document_definition("app"),)),
        signatures_config=SignaturesConfig(slots=slots, route=route),
        pack_submission=PackSubmissionConfig(profiles=(profile,) if profile else ()),
        supported_staffing=("solo", "team"),
    )


def _project(version: TemplateVersion, *, team: bool = False, kind: ProjectKind = ProjectKind.research) -> Project:
    staffing = ProjectStaffing.team if team else ProjectStaffing.solo
    authors = _TEAM if team else [Author(name="Шалаев Алексей")]
    docs = _build_documents(version, None, staffing, authors, shared_enabled=True, kind=kind)
    return replace(make_project(documents=docs), staffing=staffing, authors=authors, kind=kind)


# ── route_order: id слотов каталога ──


def test__route_order__no_pack_route__builtin_order_of_catalog_slots() -> None:
    assert route_order(_version()) == BUILTIN_ROUTE


def test__route_order__version_route__replaces_builtin() -> None:
    version = _version(route=(("author",), ("supervisor",), ("co_supervisor", "academic_supervisor")))

    assert route_order(version) == (("author",), ("supervisor",), ("co_supervisor", "academic_supervisor"))


def test__route_order__profile_route__overrides_version_route() -> None:
    profile = _profile(("author",), route=(("author",), ("supervisor",), ("co_supervisor",), ("academic_supervisor",)))
    version = _version(route=(("author", "supervisor"),), profile=profile)

    assert route_order(version, profile) == (("author",), ("supervisor",), ("co_supervisor",), ("academic_supervisor",))


def test__route_order__slot_missing_from_route__goes_last_as_its_own_step() -> None:
    version = _version(route=(("supervisor",), ("author",)))

    assert route_order(version) == (("supervisor",), ("author",), ("co_supervisor",), ("academic_supervisor",))


def test__route_order__unknown_and_repeated_ids__skipped_first_mention_wins() -> None:
    version = _version(route=(("ghost", "author"), ("author", "supervisor"), ("ghost",), ("supervisor",)))

    assert route_order(version) == (("author",), ("supervisor",), ("co_supervisor",), ("academic_supervisor",))


def test__route_order__builtin_names_absent_slots__keeps_only_catalog_slots() -> None:
    version = _version(slots=(_slot("author", per_author=True), _slot("supervisor"), _slot("reviewer")))

    assert route_order(version) == (("author",), ("supervisor",), ("reviewer",))


def test__route_order__no_slots__empty() -> None:
    assert route_order(_version(slots=())) == ()


# ── default_route: персоны подписантов точки в проекте ──


def test__default_route__solo__personas_of_required_slots_only() -> None:
    profile = _profile(("author", "supervisor"))
    version = _version(profile=profile)

    assert default_route(version, profile, _project(version)) == (("author",), ("supervisor",))


def test__default_route__optional_slots_passed__take_their_steps() -> None:
    profile = _profile(("author", "supervisor"))
    version = _version(profile=profile)
    slots = ["academic_supervisor", "supervisor", "author", "co_supervisor"]

    route = default_route(version, profile, _project(version), slot_ids=slots)

    assert route == (("author",), ("supervisor", "co_supervisor"), ("academic_supervisor",))


def test__default_route__team__per_author_slot_expands_into_one_step_of_all_authors() -> None:
    profile = _profile(("author", "supervisor"))
    version = _version(profile=profile)

    assert default_route(version, profile, _project(version, team=True)) == (("shalaev", "ivanov"), ("supervisor",))


def test__default_route__profile_route__orders_personas() -> None:
    profile = _profile(("author", "supervisor", "co_supervisor"), route=(("supervisor", "co_supervisor"), ("author",)))
    version = _version(profile=profile)

    assert default_route(version, profile, _project(version)) == (("supervisor", "co_supervisor"), ("author",))


def test__default_route__persona_with_slots_on_two_steps__stays_on_the_first() -> None:
    # Слот без суффикса и не руководителя подписывает автор (slot_persona): участник один, шаг его первого слота.
    profile = _profile(("author", "supervisor", "receipt"))
    version = _version(slots=(*_SSE_SLOTS, _slot("receipt")), profile=profile)

    assert default_route(version, profile, _project(version)) == (("author",), ("supervisor",))


def test__default_route__slot_outside_catalog__kept_as_last_step() -> None:
    # Каталог версии сменился, а слот остался в маршруте: участник не теряется.
    profile = _profile(("author",))
    version = _version(slots=(_slot("author", per_author=True), _slot("supervisor")), profile=profile)

    route = default_route(version, profile, _project(version), slot_ids=["academic_supervisor", "author"])

    assert route == (("author",), ("academic_supervisor",))


def test__default_route__profile_without_signatures__empty() -> None:
    profile = _profile(())
    version = _version(profile=profile)

    assert default_route(version, profile, _project(version)) == ()


def test__default_route__item_of_another_kind__not_in_route() -> None:
    profile = replace(
        _profile(()),
        items=(SubmissionDocItem(doc_id="app", signatures=("author", "supervisor"), supported_kinds=("project",)),),
    )
    version = _version(profile=profile)

    assert default_route(version, profile, _project(version, kind=ProjectKind.research)) == ()


# ── реальные паки: встроенный порядок подходит выпущенным версиям, их каталоги не меняются ──


@pytest.fixture(scope="module")
def templates() -> YamlTemplateRepository:
    return YamlTemplateRepository(_PACKS)


def _real(templates: YamlTemplateRepository, pack: str, template: str, version: str) -> TemplateVersion:
    found = templates.get_version(pack, template, version)
    assert found is not None
    return found


def _profile_of(version: TemplateVersion, profile_id: str) -> SubmissionProfile:
    return next(p for p in version.pack_submission.profiles if p.id == profile_id)


def test__real_packs__builtin_order_places_every_slot(templates: YamlTemplateRepository) -> None:
    """Ни одна выпущенная версия не задаёт порядок, и ни один её слот не уходит в хвост встроенного."""
    builtin = {slot_id for step in BUILTIN_ROUTE for slot_id in step}
    for pack in templates.list_packs():
        for template in pack.templates:
            for version_id in templates.list_versions(pack.id, template.id):
                version = _real(templates, pack.id, template.id, version_id)
                assert version.signatures_config.route == ()
                assert all(p.signing_route == () for p in version.pack_submission.profiles)
                assert {s.id for s in version.signatures_config.slots} <= builtin, f"{pack.id}/{version_id}"


def test__sse_topic_approval__author_then_supervisor(templates: YamlTemplateRepository) -> None:
    version = _real(templates, "hse-cs-sse", "coursework", "2026.1.3")
    profile = _profile_of(version, "topic-approval")
    project = _project(version)

    assert default_route(version, profile, project) == (("author",), ("supervisor",))
    # Академрук и консультант на заявлении необязательны: автор добавляет их сам, шаги берутся из порядка.
    with_optional = ["author", "supervisor", "co_supervisor", "academic_supervisor"]
    assert default_route(version, profile, project, slot_ids=with_optional) == (
        ("author",),
        ("supervisor", "co_supervisor"),
        ("academic_supervisor",),
    )


def test__se_vkr_final__team__all_authors_then_supervisor(templates: YamlTemplateRepository) -> None:
    version = _real(templates, "hse-cs-se", "vkr", "2026.1")
    profile = _profile_of(version, "final")

    route = default_route(version, profile, _project(version, team=True, kind=ProjectKind.project))

    assert route == (("shalaev", "ivanov"), ("supervisor",))


def test__se_coursework_final__solo__author_only(templates: YamlTemplateRepository) -> None:
    version = _real(templates, "hse-cs-se", "coursework", "2026.1")

    assert default_route(version, _profile_of(version, "final"), _project(version)) == (("author",),)
