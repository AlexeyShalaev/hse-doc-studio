"""Места подписей из пака по документам и их происхождение (docs/design/signing-route.md, 15.3, 15.4 и 15.10)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.catalog import SignatureDefaultDate, SignatureDefaultPlacement, SignatureSlotDef
from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat, PlacementOrigin
from hse_doc_studio.core.signatures.pack_places import (
    clear_from_pack,
    keep_from_pack,
    pack_digest,
    place_digest,
    placement_digest,
    placement_origin,
    same_place,
    seed_places,
    stamp_from_pack,
)
from hse_doc_studio.core.signatures.stamps import PLATE_MIN_WIDTH_MM, widen_for_plate
from hse_doc_studio.core.value_objects import DateMark, FromPack, SignaturePlacement, SignaturesState

GENERAL = SignatureDefaultPlacement(page=1, x_mm=110, y_mm=130, width_mm=40)
PROPOSAL = SignatureDefaultPlacement(page=1, x_mm=80, y_mm=139, width_mm=40)
DAY = SignatureDefaultDate(page=1, x_mm=81, y_mm=156, width_mm=7, height_mm=5, format=DateMarkFormat.day)
MONTH = SignatureDefaultDate(page=1, x_mm=90, y_mm=156, width_mm=24, height_mm=5, format=DateMarkFormat.month_word)


def _slot(**kwargs: object) -> SignatureSlotDef:
    fields: dict[str, object] = {
        "id": "supervisor",
        "label": {"ru": "Научный руководитель"},
        "applies_to": ("project_proposal", "topic_application", "report"),
        "default_placement": GENERAL,
        "placements": (("project_proposal", PROPOSAL),),
        "default_dates": (("project_proposal", (DAY, MONTH)),),
    }
    fields.update(kwargs)
    return SignatureSlotDef(**fields)  # type: ignore[arg-type]


def _placement(place: SignatureDefaultPlacement, **kwargs: object) -> SignaturePlacement:
    fields: dict[str, object] = {
        "enabled": False,
        "page": place.page,
        "x_mm": place.x_mm,
        "y_mm": place.y_mm,
        "width_mm": place.width_mm,
    }
    fields.update(kwargs)
    return SignaturePlacement(**fields)  # type: ignore[arg-type]


def _mark(source: SignatureDefaultDate, mark_id: str) -> DateMark:
    return DateMark(
        id=mark_id,
        page=source.page,
        x_mm=source.x_mm,
        y_mm=source.y_mm,
        width_mm=source.width_mm,
        height_mm=source.height_mm,
        format=source.format,
        align=source.align,
    )


def test__place_for__document_entry_else_default_placement() -> None:
    slot = _slot()

    assert slot.place_for("project_proposal") == PROPOSAL
    assert slot.place_for("report") == GENERAL
    assert slot.dates_for("project_proposal") == (DAY, MONTH)
    assert slot.dates_for("report") == ()


def test__place_digest__rounds_to_a_tenth_ignores_mark_ids_and_order() -> None:
    marks = (_mark(DAY, "d1"), _mark(MONTH, "d2"))
    renamed = (_mark(MONTH, "d7"), _mark(DAY, "d9"))

    base = place_digest(1, 80, 139, 40, marks)

    assert len(base) == 16
    assert place_digest(1, 80.04, 138.96, 40.0, renamed) == base
    assert place_digest(1, 80.2, 139, 40, marks) != base
    assert place_digest(2, 80, 139, 40, marks) != base
    assert place_digest(1, 80, 139, 40, marks[:1]) != base
    assert place_digest(1, 80, 139, 40, (replace(marks[0], align=DateMarkAlign.left), marks[1])) != base


def test__pack_digest__equals_digest_of_the_place_with_pack_marks() -> None:
    placement = _placement(PROPOSAL, dates=(_mark(DAY, "d1"), _mark(MONTH, "d2")))

    assert pack_digest(_slot(), "project_proposal") == placement_digest(placement)
    assert pack_digest(_slot(), "report") == placement_digest(_placement(GENERAL))


def test__same_place__within_a_tenth_of_a_millimetre_on_the_same_page() -> None:
    assert same_place(_placement(PROPOSAL, x_mm=80.05), PROPOSAL)
    assert not same_place(_placement(PROPOSAL, x_mm=80.2), PROPOSAL)
    assert not same_place(_placement(PROPOSAL, page=2), PROPOSAL)


def test__placement_origin__from_pack_with_matching_digest__pack_even_when_enabled() -> None:
    placement = stamp_from_pack(_placement(PROPOSAL, enabled=True, dates=(_mark(DAY, "d1"),)), "2026.1.4")

    assert placement.from_pack == FromPack(version="2026.1.4", digest=placement_digest(placement))
    assert placement_origin(placement, ()) is PlacementOrigin.pack
    # Включение и дата в рамке в отпечаток не входят: место остаётся из шаблона.
    assert placement_origin(replace(placement, enabled=False, sign_date="2026-11-13"), ()) is PlacementOrigin.pack


@pytest.mark.parametrize(
    "change",
    [{"x_mm": 85.0}, {"width_mm": 30.0}, {"page": 2}, {"dates": ()}],
)
def test__placement_origin__moved_after_the_pack_placed_it__manual(change: dict[str, object]) -> None:
    placement = stamp_from_pack(_placement(PROPOSAL, dates=(_mark(DAY, "d1"),)), "2026.1.4")

    assert placement_origin(replace(placement, **change), seed_places([_slot()], "project_proposal")) is (
        PlacementOrigin.manual
    )


def test__placement_origin__unmarked_disabled_place_of_any_known_version__seed() -> None:
    earlier = _slot(placements=(), default_dates=(), default_placement=SignatureDefaultPlacement(1, 60, 230, 50))
    seeds = seed_places([_slot(), earlier], "project_proposal")

    assert placement_origin(_placement(PROPOSAL), seeds) is PlacementOrigin.seed
    assert placement_origin(_placement(GENERAL), seeds) is PlacementOrigin.seed
    assert placement_origin(_placement(SignatureDefaultPlacement(1, 60, 230, 50)), seeds) is PlacementOrigin.seed


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": True},
        {"sign_date": "2026-11-13"},
        {"dates": (_mark(DAY, "d1"),)},
        {"x_mm": 81.0},
        {"from_pack": FromPack(version="2026.1.4", digest="0" * 16)},
    ],
)
def test__placement_origin__touched_seed__manual(change: dict[str, object]) -> None:
    seeds = seed_places([_slot()], "project_proposal")

    assert placement_origin(_placement(PROPOSAL, **change), seeds) is PlacementOrigin.manual


def test__keep_from_pack__restamps_a_pack_place_and_leaves_manual_ones() -> None:
    from_pack = stamp_from_pack(_placement(PROPOSAL, enabled=True), "2026.1.4")
    moved = replace(from_pack, x_mm=50.0)

    kept = keep_from_pack(from_pack, replace(from_pack, x_mm=50.0, width_mm=70.0))

    assert placement_origin(kept, ()) is PlacementOrigin.pack
    assert kept.from_pack is not None
    assert kept.from_pack.version == "2026.1.4"
    assert keep_from_pack(moved, replace(moved, width_mm=70.0)).from_pack == moved.from_pack
    assert clear_from_pack(from_pack).from_pack is None


def test__widen_for_plate__place_from_the_pack_stays_from_the_pack() -> None:
    placement = stamp_from_pack(_placement(PROPOSAL, enabled=True, width_mm=30.0), "2026.1.4")
    state = SignaturesState(slots={}, placements={"proposal": {"supervisor": placement}})

    widened = widen_for_plate(state, [("proposal", "supervisor")]).placements["proposal"]["supervisor"]

    assert widened.width_mm == PLATE_MIN_WIDTH_MM
    assert widened.x_mm + widened.width_mm == placement.x_mm + placement.width_mm
    assert placement_origin(widened, ()) is PlacementOrigin.pack
