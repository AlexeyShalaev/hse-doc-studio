"""Места авторов команды на общем документе по якорям на каждого автора (docs/design/signing-route.md, 15.17.20).

Пресет маршрута, пересчёт после сборки и состояние якоря места: экземпляр автора `author--<слаг>` встаёт на свою
строку `author__<слаг>`; старая сборка с одним якорем `author` ведёт себя как раньше (пресет такие места не ставит,
пересборка их не двигает).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import pytest
from hse_doc_studio.core.catalog import (
    AnchorPlace,
    SignatureDefaultPlacement,
    SignaturesConfig,
    SignatureSlotDef,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import AnchorState, DateMarkAlign, ProjectStaffing
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors
from hse_doc_studio.core.signatures.pack_places import SourceAnchors, is_from_pack, pack_placement
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.value_objects import Author, SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.signatures.anchor_places import rebuild_places
from hse_doc_studio.use_cases.signatures.pack_places import PackPlaces
from hse_doc_studio.use_cases.signing_route.point import RoutePoint
from hse_doc_studio.use_cases.signing_route.preset import FRESH_ORIGINS, apply_places

from tests.factories import make_document, make_project, make_template_version

pytestmark = pytest.mark.unit

V = "2026.1.6"
DOC = "shared_technical_specification"
GENERAL = SignatureDefaultPlacement(page=1, x_mm=104, y_mm=233, width_mm=35)
SLOT = SignatureSlotDef(
    id="author",
    label={"ru": "Автор работы"},
    applies_to=(DOC,),
    default_placement=GENERAL,
    per_author=True,
    placements=((DOC, AnchorPlace("author", align=DateMarkAlign.centered, dy_mm=-11, width_mm=35, fallback=GENERAL)),),
)
VERSION: TemplateVersion = replace(make_template_version(version=V), signatures_config=SignaturesConfig(slots=(SLOT,)))
IVANOV = BuildAnchor("author__ivanov", AnchorKind.sign, 1, 104.0, 230.0, 70.0)
PETROV = BuildAnchor("author__petrov", AnchorKind.sign, 1, 104.0, 252.0, 70.0)
OLD = BuildAnchor("author", AnchorKind.sign, 1, 104.0, 230.0, 70.0)
OLD_MOVED = BuildAnchor("author", AnchorKind.sign, 1, 104.0, 240.0, 70.0)
PAIRS = (DocSlot(DOC, "author--ivanov"), DocSlot(DOC, "author--petrov"))


def _src(*lines: BuildAnchor) -> SourceAnchors:
    return SourceAnchors(BuildAnchors("d" * 64, lines))


def _project() -> Project:
    return replace(
        make_project(documents=[make_document(DOC)]),
        staffing=ProjectStaffing.team,
        authors=[Author(name="Иванов Иван", slug="ivanov"), Author(name="Петров Пётр", slug="petrov")],
    )


def _doc(project: Project) -> Document:
    return project.documents[0]


def _point(project: Project) -> RoutePoint:
    return RoutePoint(
        project=project,
        version=VERSION,
        profile=cast(Any, None),
        required=PAIRS,
        allowed={},
        runtime={slot.id: slot for slot in SignatureSlotService().runtime_slots(project, VERSION)},
        documents={doc.id: doc for doc in project.documents},
        doc_names={},
    )


def _old_place() -> SignaturePlacement:
    """Место из шаблона на строке первого автора: так его ставили «Вернуть место из шаблона» и затравка картинки."""
    placement = pack_placement(SLOT, DOC, None, V, _src(OLD))
    assert placement is not None
    return replace(placement, enabled=True)


def _state(placement: SignaturePlacement) -> SignaturesState:
    return SignaturesState(slots={}, placements={DOC: {"author--ivanov": placement, "author--petrov": placement}})


def _xy(state: SignaturesState, slot_id: str) -> tuple[float, float]:
    placement = state.placements[DOC][slot_id]
    return placement.x_mm, placement.y_mm


# --- пресет маршрута ---


def test__preset__each_author_on_own_line() -> None:
    project = _project()
    anchors = {DOC: _src(IVANOV, PETROV)}

    state, placed = apply_places(
        _point(project),
        SignaturesState(slots={}, placements={}),
        PAIRS,
        PackPlaces(project, VERSION, anchors=anchors),
        origins=FRESH_ORIGINS,
        anchors=anchors,
    )

    assert placed == PAIRS
    assert _xy(state, "author--ivanov") == (121.5, 219.0)
    assert _xy(state, "author--petrov") == (121.5, 241.0)
    assert all(state.placements[DOC][pair.slot_id].enabled for pair in PAIRS)
    assert all(is_from_pack(state.placements[DOC][pair.slot_id]) for pair in PAIRS)


@pytest.mark.parametrize("src", [_src(OLD), SourceAnchors()], ids=["one_author_anchor", "unknown_anchors"])
def test__preset__old_build__no_place_as_before(src: SourceAnchors) -> None:
    project = _project()
    anchors = {DOC: src}
    empty = SignaturesState(slots={}, placements={})

    state, placed = apply_places(
        _point(project),
        empty,
        PAIRS,
        PackPlaces(project, VERSION, anchors=anchors),
        origins=FRESH_ORIGINS,
        anchors=anchors,
    )

    assert placed == ()
    assert state == empty


def test__preset__place_from_the_old_line_moves_to_the_author_line() -> None:
    project = _project()
    anchors = {DOC: _src(IVANOV, PETROV)}

    state, placed = apply_places(
        _point(project),
        _state(_old_place()),
        PAIRS,
        PackPlaces(project, VERSION, anchors=anchors),
        origins=FRESH_ORIGINS,
        anchors=anchors,
    )

    assert placed == (PAIRS[1],)  # Иванов и так стоял на первой строке
    assert _xy(state, "author--petrov") == (121.5, 241.0)


# --- пересчёт после сборки ---


def test__rebuild__places_of_the_authors_follow_their_lines() -> None:
    project = _project()

    rebuilt = rebuild_places(_state(_old_place()), project, VERSION, _doc(project), _src(IVANOV, PETROV))

    assert _xy(rebuilt, "author--ivanov") == (121.5, 219.0)
    assert _xy(rebuilt, "author--petrov") == (121.5, 241.0)
    assert is_from_pack(rebuilt.placements[DOC]["author--petrov"])


def test__rebuild__author_line_gone__his_place_switched_off() -> None:
    project = _project()

    rebuilt = rebuild_places(_state(_old_place()), project, VERSION, _doc(project), _src(IVANOV))

    assert rebuilt.placements[DOC]["author--ivanov"].enabled
    assert not rebuilt.placements[DOC]["author--petrov"].enabled


def test__rebuild__old_build__shared_author_places_not_touched_as_before() -> None:
    project = _project()
    state = _state(_old_place())

    assert rebuild_places(state, project, VERSION, _doc(project), _src(OLD_MOVED)) == state


# --- состояние якоря места в ответе API ---


def test__place_info__anchor_of_the_author_line() -> None:
    project = _project()
    places = PackPlaces(project, VERSION, anchors={DOC: _src(IVANOV)})
    old = PackPlaces(project, VERSION, anchors={DOC: _src(OLD)})

    ivanov, petrov = places.anchor(DOC, "author--ivanov"), places.anchor(DOC, "author--petrov")

    assert ivanov is not None
    assert ivanov.state is AnchorState.found
    assert petrov is not None
    assert petrov.state is AnchorState.missing
    assert old.anchor(DOC, "author--petrov") == old.anchor(DOC, "author--ivanov")
