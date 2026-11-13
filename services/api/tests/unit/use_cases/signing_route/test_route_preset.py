"""Пресет маршрута точки: состав с условиями, отличия, применение к состоянию подписей (signing-route.md, 15.5, 15.6).

Пак: `hse-cs-sse` 2026.1.3 с ключами 2026.1.4 (`preset_world`), точка «Заявка на тему КП».
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from uuid import uuid4

import pytest
from hse_doc_studio.core.catalog import SigningSlotPreset
from hse_doc_studio.core.enums import PersonRole, PlacementOrigin, SignMode
from hse_doc_studio.core.signatures.pack_places import is_from_pack, pack_digest, stamp_from_pack
from hse_doc_studio.core.signing_route.drafting import apply_people
from hse_doc_studio.core.signing_route.entities import DocSlot, Participant, SigningRoute
from hse_doc_studio.core.signing_route.preset import (
    PresetDiff,
    condition_met,
    preset_differs,
    preset_people,
)
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    FrozenPdf,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
    SkippedSlot,
)
from hse_doc_studio.use_cases.signatures.pack_places import PackPlaces
from hse_doc_studio.use_cases.signing_route.preset import (
    FRESH_ORIGINS,
    INHERITED_ORIGINS,
    apply_optional,
    apply_places,
    route_preset,
)

from tests.unit.use_cases.signing_route.preset_world import (
    ACADEMIC_WHEN,
    APPLICATION,
    APPLICATION_PLACE,
    CONSULTANT_WHEN,
    PROPOSAL,
    PROPOSAL_PLACE,
    point,
    preset_version,
    project,
    released,
)

pytestmark = pytest.mark.unit

SUPERVISOR_PROPOSAL = DocSlot(PROPOSAL, "supervisor")
SUPERVISOR_APPLICATION = DocSlot(APPLICATION, "supervisor")
AUTHOR_APPLICATION = DocSlot(APPLICATION, "author")
CONSULTANT = DocSlot(APPLICATION, "co_supervisor")
ACADEMIC = DocSlot(APPLICATION, "academic_supervisor")
POINT_PAIRS = (SUPERVISOR_PROPOSAL, AUTHOR_APPLICATION, SUPERVISOR_APPLICATION)


def _state(**fields: Any) -> SignaturesState:
    return SignaturesState(**{"slots": {}, "placements": {}, **fields})


def _places(version: object, proj: object) -> PackPlaces:
    return PackPlaces(proj, version)  # type: ignore[arg-type]


# ── условия и состав ────────────────────────────────────────────────────────────────────────────────────────────────


def test__condition__person_and_role_of_the_project() -> None:
    version = preset_version()
    hse = project(version)
    company = project(version, supervisor=PersonRole.company, consultant=True)
    nobody = project(version, supervisor=None)

    assert condition_met(None, hse)
    assert not condition_met(CONSULTANT_WHEN, hse)
    assert condition_met(CONSULTANT_WHEN, company)
    assert not condition_met(ACADEMIC_WHEN, hse)
    assert condition_met(ACADEMIC_WHEN, company)
    assert not condition_met(ACADEMIC_WHEN, nobody)


def test__preset__supervisor_from_hse__academic_skipped_by_condition() -> None:
    version = preset_version()

    preset = route_preset(point(version, project(version)))

    assert preset is not None
    assert preset.version == "2026.1.4"
    assert preset.steps == (("author",), ("supervisor",))
    assert preset.extra_slots == ()
    assert [(item.pair, item.when) for item in preset.skipped_by_condition] == [
        (CONSULTANT, CONSULTANT_WHEN),
        (ACADEMIC, ACADEMIC_WHEN),
    ]
    assert preset.optional == ()


def test__preset__supervisor_from_company_with_consultant__both_extra_slots_on_their_steps() -> None:
    version = preset_version()

    preset = route_preset(point(version, project(version, supervisor=PersonRole.company, consultant=True)))

    assert preset is not None
    assert preset.extra_pairs == (CONSULTANT, ACADEMIC)
    assert preset.steps == (("author",), ("supervisor", "co_supervisor"), ("academic_supervisor",))
    assert preset.skipped_by_condition == ()


def test__preset__optional_on_point_pair_and_extra__required_slot_and_unknown_entries_skipped() -> None:
    entries = (
        SigningSlotPreset(doc_id=PROPOSAL, slot_id="supervisor", optional=True),
        SigningSlotPreset(doc_id=APPLICATION, slot_id="academic_supervisor", optional=True),
        # Неприменимые записи лоадер не отбрасывает: пресет их молча пропускает.
        SigningSlotPreset(doc_id="report", slot_id="author", optional=True),
        SigningSlotPreset(doc_id=PROPOSAL, slot_id="author"),
        SigningSlotPreset(doc_id=APPLICATION, slot_id="nobody"),
    )
    version = preset_version(signing_slots=entries)
    slots = tuple(replace(s, required=True) if s.id == "author" else s for s in version.signatures_config.slots)
    version = replace(version, signatures_config=replace(version.signatures_config, slots=slots))
    entries_with_required = (*entries, SigningSlotPreset(doc_id=APPLICATION, slot_id="author", optional=True))
    profiles = tuple(
        replace(p, signing_slots=entries_with_required) if p.id == "topic-approval" else p
        for p in version.pack_submission.profiles
    )
    version = replace(version, pack_submission=replace(version.pack_submission, profiles=profiles))

    preset = route_preset(point(version, project(version)))

    assert preset is not None
    assert preset.extra_pairs == (ACADEMIC,)
    assert preset.optional == (SUPERVISOR_PROPOSAL, ACADEMIC)
    assert preset.steps == (("author",), ("supervisor",), ("academic_supervisor",))


def test__preset__released_pack__none() -> None:
    version = released()

    assert route_preset(point(version, project(version))) is None


def test__preset__places_only__preset_without_extra_slots() -> None:
    version = preset_version(signing_slots=())

    preset = route_preset(point(version, project(version)))

    assert preset is not None
    assert (preset.extra_slots, preset.optional, preset.steps) == ((), (), (("author",), ("supervisor",)))


# ── отличия и люди ──────────────────────────────────────────────────────────────────────────────────────────────────


def _route(*people: tuple[int, str, tuple[DocSlot, ...]]) -> SigningRoute:
    return SigningRoute(
        id=uuid4(),
        project_id=uuid4(),
        profile_id="topic-approval",
        created_by=uuid4(),
        participants=tuple(
            Participant(id=uuid4(), step=step, persona=persona, user_id=uuid4(), assignments=pairs)
            for step, persona, pairs in people
        ),
        docs=(PROPOSAL, APPLICATION),
    )


def test__differs__as_in_template__empty_and_each_kind_found() -> None:
    version = preset_version()
    preset = route_preset(point(version, project(version, supervisor=PersonRole.company)))
    assert preset is not None
    same = _route(
        (1, "author", (AUTHOR_APPLICATION,)),
        (2, "supervisor", (SUPERVISOR_PROPOSAL, SUPERVISOR_APPLICATION)),
        (3, "academic_supervisor", (ACADEMIC,)),
    )
    reordered = _route(
        (1, "author", (AUTHOR_APPLICATION,)),
        (1, "supervisor", (SUPERVISOR_PROPOSAL, SUPERVISOR_APPLICATION)),
        (2, "academic_supervisor", (ACADEMIC,)),
    )
    without_academic = _route(
        (1, "author", (AUTHOR_APPLICATION,)), (2, "supervisor", (SUPERVISOR_PROPOSAL, SUPERVISOR_APPLICATION))
    )

    assert preset_differs(preset, same, POINT_PAIRS, ()) == ()
    assert preset_differs(preset, reordered, POINT_PAIRS, ()) == (PresetDiff.order,)
    assert preset_differs(preset, without_academic, POINT_PAIRS, ()) == (PresetDiff.order, PresetDiff.slots)
    assert preset_differs(preset, same, POINT_PAIRS, (SUPERVISOR_PROPOSAL,)) == (PresetDiff.optional,)
    # Отметка у пары вне маршрута в сравнение не входит.
    assert preset_differs(preset, same, POINT_PAIRS, (CONSULTANT,)) == ()


def test__preset_people__kept_by_persona_with_approval__extra_dropped__missing_added() -> None:
    author = Participant(id=uuid4(), step=1, persona="author", user_id=uuid4())
    supervisor = Participant(id=uuid4(), step=1, persona="supervisor", user_id=uuid4(), approval=None)
    second = Participant(id=uuid4(), step=2, persona="supervisor", user_id=uuid4())
    consultant = Participant(id=uuid4(), step=3, persona="co_supervisor", user_id=uuid4())
    current = (author, supervisor, second, consultant)

    people = apply_people(current, preset_people(current, (("author",), ("supervisor",), ("academic_supervisor",))))

    assert [(p.step, p.persona) for p in people] == [(1, "author"), (2, "supervisor"), (3, "academic_supervisor")]
    assert (people[0], people[1].id, people[1].user_id) == (author, supervisor.id, supervisor.user_id)
    assert people[2].user_id is None
    assert people[2].invitation_id is None


# ── места и метки даты ──────────────────────────────────────────────────────────────────────────────────────────────


def test__places__new_pairs__pack_place_dates_enabled_and_stamped() -> None:
    version = preset_version()
    proj = project(version)
    pt = point(version, proj)

    state, placed = apply_places(pt, _state(), POINT_PAIRS, _places(version, proj), origins=FRESH_ORIGINS)

    assert placed == POINT_PAIRS
    proposal = state.placements[PROPOSAL]["supervisor"]
    assert (proposal.page, proposal.x_mm, proposal.y_mm, proposal.width_mm) == (1, 80, 139, 40)
    assert [(m.id, m.format.value) for m in proposal.dates] == [("d1", "day"), ("d2", "month_word")]
    assert proposal.enabled
    assert is_from_pack(proposal)
    assert proposal.from_pack is not None
    assert proposal.from_pack.version == "2026.1.4"
    assert proposal.from_pack.digest == pack_digest(pt.runtime["supervisor"].slot_def, PROPOSAL)
    application = state.placements[APPLICATION]["supervisor"]
    assert (application.x_mm, application.y_mm, application.dates) == (163, 168, ())


def test__places__manual_untouched__seed_and_pack_replaced__repeat_is_noop() -> None:
    version = preset_version()
    proj = project(version)
    pt = point(version, proj)
    manual = SignaturePlacement(enabled=True, page=1, x_mm=50, y_mm=50, width_mm=40)
    # Затравка по общему месту выпущенной версии и место из шаблона другой версии.
    seed = SignaturePlacement(enabled=False, page=1, x_mm=110, y_mm=130, width_mm=40)
    old_pack = stamp_from_pack(SignaturePlacement(enabled=True, page=1, x_mm=160, y_mm=208, width_mm=30), "2026.1.3")
    state = _state(placements={PROPOSAL: {"supervisor": manual}, APPLICATION: {"supervisor": seed, "author": old_pack}})

    first, placed = apply_places(pt, state, POINT_PAIRS, _places(version, proj), origins=FRESH_ORIGINS)
    second, again = apply_places(pt, first, POINT_PAIRS, _places(version, proj), origins=FRESH_ORIGINS)

    assert placed == (AUTHOR_APPLICATION, SUPERVISOR_APPLICATION)
    assert first.placements[PROPOSAL]["supervisor"] == manual
    assert first.placements[APPLICATION]["supervisor"].x_mm == APPLICATION_PLACE.x_mm
    assert first.placements[APPLICATION]["supervisor"].enabled
    assert first.placements[APPLICATION]["author"].x_mm == 165
    assert (second, again) == (first, ())


def test__places__inherited_draft__only_pairs_without_place_or_seed() -> None:
    version = preset_version()
    proj = project(version)
    pt = point(version, proj)
    old_pack = stamp_from_pack(SignaturePlacement(enabled=True, page=1, x_mm=160, y_mm=208, width_mm=30), "2026.1.3")
    state = _state(placements={APPLICATION: {"author": old_pack}})

    updated, placed = apply_places(pt, state, POINT_PAIRS, _places(version, proj), origins=INHERITED_ORIGINS)

    assert placed == (SUPERVISOR_PROPOSAL, SUPERVISOR_APPLICATION)
    assert updated.placements[APPLICATION]["author"] == old_pack


def test__places__other_route_doc_and_signed_frozen_doc__untouched() -> None:
    version = preset_version()
    proj = project(version)
    pt = point(version, proj)
    # Над зафиксированным «Заявлением» есть ЭП: новое место устарило бы фиксацию. Содержимое записей не важно.
    frozen = cast(FrozenPdf, object())
    signed = cast(DetachedSignature, object())
    state = _state(frozen={APPLICATION: frozen}, detached={APPLICATION: {"supervisor": signed}})

    updated, placed = apply_places(
        pt, state, POINT_PAIRS, _places(version, proj), origins=FRESH_ORIGINS, skip_docs={PROPOSAL}
    )

    assert placed == ()
    assert updated == state


def test__places__pades_only_slot__place_written_but_not_enabled() -> None:
    version = preset_version()
    proj = project(version)
    pt = point(version, proj)
    state = _state(slots={"supervisor": SignatureSlot(None, None, None, sign_mode=SignMode.crypto_invisible)})
    # Точка разрешает PAdES научруку на «Описании проекта»: способ слота принят, метки не будет.
    pt = replace(pt, allowed={**pt.allowed, SUPERVISOR_PROPOSAL: ("pades",)})

    updated, placed = apply_places(pt, state, (SUPERVISOR_PROPOSAL,), _places(version, proj), origins=FRESH_ORIGINS)

    assert placed == (SUPERVISOR_PROPOSAL,)
    placement = updated.placements[PROPOSAL]["supervisor"]
    assert (placement.enabled, placement.x_mm, len(placement.dates)) == (False, PROPOSAL_PLACE.x_mm, 2)


def test__places__origin_of_written_place_is_pack() -> None:
    version = preset_version()
    proj = project(version)
    pt = point(version, proj)
    places = _places(version, proj)

    updated, _ = apply_places(pt, _state(), POINT_PAIRS, places, origins=FRESH_ORIGINS)

    assert {places.info(d, s, p).origin for d, m in updated.placements.items() for s, p in m.items()} == {
        PlacementOrigin.pack
    }


# ── отметки «необязательна» ─────────────────────────────────────────────────────────────────────────────────────────


def _optional_preset(proj_supervisor: PersonRole = PersonRole.university) -> tuple[object, object]:
    entries = (SigningSlotPreset(doc_id=PROPOSAL, slot_id="supervisor", optional=True),)
    version = preset_version(signing_slots=entries)
    pt = point(version, project(version, supervisor=proj_supervisor))
    preset = route_preset(pt)
    assert preset is not None
    return pt, preset


def test__optional__set_by_preset__existing_marks_kept_on_create() -> None:
    pt, preset = _optional_preset()
    state = _state(optional={APPLICATION: {"topic-approval": frozenset({"author"})}})

    updated, marked, unmarked = apply_optional(pt, state, POINT_PAIRS, preset, unset=False)  # type: ignore[arg-type]

    assert (marked, unmarked) == ((SUPERVISOR_PROPOSAL,), ())
    assert updated.is_optional(PROPOSAL, "topic-approval", "supervisor")
    assert updated.is_optional(APPLICATION, "topic-approval", "author")


def test__optional__restore_unsets_and_drops_skip_only_when_route_does_not_hold_doc() -> None:
    pt, preset = _optional_preset()
    skip = SkippedSlot(profile_id="topic-approval", route_id="r", round=1, at="2026-11-13T10:00:00+00:00")
    state = _state(
        optional={APPLICATION: {"topic-approval": frozenset({"author"})}},
        skipped={APPLICATION: {"author": skip}},
    )

    free, _, unmarked = apply_optional(pt, state, POINT_PAIRS, preset, unset=True)  # type: ignore[arg-type]
    held, _, _ = apply_optional(pt, state, POINT_PAIRS, preset, unset=True, held={APPLICATION})  # type: ignore[arg-type]

    assert unmarked == (AUTHOR_APPLICATION,)
    assert not free.is_optional(APPLICATION, "topic-approval", "author")
    assert free.skip_of(APPLICATION, "author") is None
    assert held.skip_of(APPLICATION, "author") == skip


def test__optional__signed_slot_on_held_doc_and_other_route_doc__not_marked() -> None:
    pt, preset = _optional_preset()

    signed, marked, _ = apply_optional(
        pt,  # type: ignore[arg-type]
        _state(),
        POINT_PAIRS,
        preset,  # type: ignore[arg-type]
        unset=False,
        held={PROPOSAL},
        signed=lambda pair: pair == SUPERVISOR_PROPOSAL,
    )
    elsewhere, marked_elsewhere, _ = apply_optional(
        pt,  # type: ignore[arg-type]
        _state(),
        POINT_PAIRS,
        preset,  # type: ignore[arg-type]
        unset=False,
        skip_docs={PROPOSAL},
    )

    assert (marked, marked_elsewhere) == ((), ())
    assert signed == elsewhere == _state()
