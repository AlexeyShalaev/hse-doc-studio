"""Места подписей и метки даты на якорях шаблона (docs/design/signing-route.md, 15.17.7, 15.17.8 и 15.17.10)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.catalog import (
    AnchorDate,
    AnchorPlace,
    SignatureDefaultDate,
    SignatureDefaultPlacement,
    SignatureSlotDef,
)
from hse_doc_studio.core.enums import AnchorState, DateMarkAlign, DateMarkFormat, PlacementOrigin, PlaceSource
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors
from hse_doc_studio.core.signatures.pack_places import (
    NO_ANCHORS,
    SourceAnchors,
    anchor_box,
    anchor_mark,
    anchor_ref,
    is_from_pack,
    keep_from_pack,
    pack_digest,
    pack_placement,
    place_digest,
    place_source,
    placement_digest,
    resolve_place,
)
from hse_doc_studio.core.value_objects import SignaturePlacement

SHA = "a" * 64
GENERAL = SignatureDefaultPlacement(page=1, x_mm=110, y_mm=130, width_mm=40)
# Замер 15.15: линия «Подпись» научрука в русском заявлении 169,5..195,0 на 186,8, в английском на 158,0.
RU_LINE = BuildAnchor("supervisor", AnchorKind.sign, 1, 169.5, 186.8, 25.5)
EN_LINE = BuildAnchor("supervisor", AnchorKind.sign, 1, 169.5, 158.0, 25.5)
DAY_LINE = BuildAnchor("supervisor.day", AnchorKind.date, 1, 81.7, 153.0, 8.0)
MONTH_LINE = BuildAnchor("supervisor.month_word", AnchorKind.date, 1, 92.6, 153.0, 25.0)


def _src(*lines: BuildAnchor, sha: str = SHA) -> SourceAnchors:
    return SourceAnchors(BuildAnchors(sha, tuple(lines)))


def _slot(**kwargs: object) -> SignatureSlotDef:
    fields: dict[str, object] = {
        "id": "supervisor",
        "label": {"ru": "Научный руководитель"},
        "applies_to": ("project_proposal", "topic_application", "report"),
        "default_placement": GENERAL,
        "placements": (("topic_application", AnchorPlace("supervisor", align=DateMarkAlign.right, width_mm=28)),),
    }
    fields.update(kwargs)
    return SignatureSlotDef(**fields)  # type: ignore[arg-type]


# --- геометрия (15.17.8) ---


@pytest.mark.parametrize(
    ("align", "dx", "x"),
    [
        (DateMarkAlign.left, 0.0, 169.5),
        (DateMarkAlign.centered, 0.0, 168.2),  # 169,5 + (25,5 - 28) / 2 = 168,25: округление банковское, до 0,1
        (DateMarkAlign.right, 0.0, 167.0),  # правые края вместе: 195,0 - 28
        (DateMarkAlign.right, 1.5, 168.5),
    ],
)
def test__anchor_box__align_and_dx(align: DateMarkAlign, dx: float, x: float) -> None:
    box = anchor_box(AnchorPlace("supervisor", align=align, dx_mm=dx, width_mm=28), RU_LINE)

    assert box == SignatureDefaultPlacement(page=1, x_mm=x, y_mm=176.8, width_mm=28)


def test__anchor_box__width_of_the_line_but_not_narrower_than_10() -> None:
    wide = anchor_box(AnchorPlace("supervisor", dy_mm=-11), RU_LINE)
    point = anchor_box(AnchorPlace("supervisor"), BuildAnchor("supervisor", AnchorKind.sign, 2, 80.0, 150.0, 0.0))

    assert wide == SignatureDefaultPlacement(page=1, x_mm=169.5, y_mm=175.8, width_mm=25.5)
    assert point == SignatureDefaultPlacement(page=2, x_mm=75.0, y_mm=140.0, width_mm=10.0)


@pytest.mark.parametrize(
    "entry",
    [
        AnchorPlace("supervisor", align=DateMarkAlign.left, dx_mm=30, width_mm=28),  # за правым краем листа
        AnchorPlace("supervisor", dy_mm=-190),  # выше верха листа
        AnchorPlace("supervisor", dy_mm=120),  # верх рамки ниже 287 мм
    ],
)
def test__anchor_box__out_of_the_page__no_place(entry: AnchorPlace) -> None:
    assert anchor_box(entry, RU_LINE) is None


def test__anchor_mark__stands_on_the_line_with_its_width() -> None:
    mark = anchor_mark(AnchorDate("supervisor.day", DateMarkFormat.day), DAY_LINE)

    assert mark == SignatureDefaultDate(
        page=1, x_mm=81.7, y_mm=148.0, width_mm=8.0, height_mm=5.0, format=DateMarkFormat.day
    )


def test__anchor_mark__point_anchor_without_width__no_mark() -> None:
    line = replace(DAY_LINE, width_mm=0.0)

    assert anchor_mark(AnchorDate("supervisor.day", DateMarkFormat.day), line) is None
    assert anchor_mark(AnchorDate("supervisor.day", DateMarkFormat.day, width_mm=7), line) is not None


# --- место на источнике (15.17.8) ---


def test__resolve_place__by_the_line_of_each_layout() -> None:
    entry = AnchorPlace("supervisor", align=DateMarkAlign.right, width_mm=28)

    ru = resolve_place(entry, _src(RU_LINE))
    en = resolve_place(entry, _src(EN_LINE))

    # Одна запись пака, две вёрстки: английская шапка короче, рамка на 28,8 мм выше.
    assert ru == SignatureDefaultPlacement(page=1, x_mm=167.0, y_mm=176.8, width_mm=28)
    assert en == SignatureDefaultPlacement(page=1, x_mm=167.0, y_mm=148.0, width_mm=28)


def test__resolve_place__known_anchors_without_the_line__no_place() -> None:
    assert resolve_place(AnchorPlace("academic_supervisor", fallback=GENERAL), _src(RU_LINE)) is None


def test__resolve_place__unknown_anchors__fallback_or_nothing() -> None:
    assert resolve_place(AnchorPlace("supervisor", fallback=GENERAL), NO_ANCHORS) == GENERAL
    assert resolve_place(AnchorPlace("supervisor"), NO_ANCHORS) is None


def test__resolve_place__own_pdf__no_place_even_with_fallback() -> None:
    own = SourceAnchors(own_pdf=True)

    assert resolve_place(AnchorPlace("supervisor", fallback=GENERAL), own) is None
    assert resolve_place(GENERAL, own) == GENERAL  # место в мм как раньше


def test__pack_placement__anchor_and_build_in_the_mark() -> None:
    placement = pack_placement(_slot(), "topic_application", None, "2026.1.5", _src(RU_LINE))

    assert placement is not None
    assert (placement.x_mm, placement.y_mm, placement.width_mm, placement.enabled) == (167.0, 176.8, 28.0, False)
    assert placement.from_pack is not None
    assert (placement.from_pack.anchor, placement.from_pack.build) == ("supervisor", SHA[:16])
    assert is_from_pack(placement)


def test__pack_placement__fallback_place_has_no_build() -> None:
    entry = AnchorPlace("supervisor", width_mm=28, fallback=SignatureDefaultPlacement(1, 168, 177, 28))
    slot = _slot(placements=(("topic_application", entry),))

    placement = pack_placement(slot, "topic_application", None, "2026.1.5", NO_ANCHORS)

    assert placement is not None
    assert (placement.x_mm, placement.y_mm) == (168, 177)
    assert placement.from_pack is not None
    assert (placement.from_pack.anchor, placement.from_pack.build) == ("supervisor", None)


def test__pack_placement__no_line__none() -> None:
    assert pack_placement(_slot(), "topic_application", None, "2026.1.5", _src()) is None


def test__pack_placement__marks_without_their_anchor_are_skipped() -> None:
    # Одна запись на русскую строку «« __ » ______» и английскую «__.__»: в сборке только русская.
    marks = (
        AnchorDate("supervisor.day", DateMarkFormat.day),
        AnchorDate("supervisor.month_word", DateMarkFormat.month_word),
        AnchorDate("supervisor.month_number", DateMarkFormat.month_number),
    )
    slot = _slot(
        placements=(("project_proposal", AnchorPlace("supervisor", align=DateMarkAlign.left, dy_mm=-14, width_mm=40)),),
        default_dates=(("project_proposal", marks),),
    )

    placement = pack_placement(
        slot,
        "project_proposal",
        None,
        "2026.1.5",
        _src(DAY_LINE, MONTH_LINE, replace(DAY_LINE, id="supervisor", kind=AnchorKind.sign)),
    )

    assert placement is not None
    assert [(m.id, m.format, m.x_mm) for m in placement.dates] == [
        ("d1", DateMarkFormat.day, 81.7),
        ("d2", DateMarkFormat.month_word, 92.6),
    ]
    assert placement.from_pack is not None
    assert placement.from_pack.build == SHA[:16]


def test__keep_from_pack__widening_keeps_the_anchor() -> None:
    placement = pack_placement(_slot(), "topic_application", None, "2026.1.5", _src(RU_LINE))
    assert placement is not None
    wide = replace(placement, x_mm=placement.x_mm - 42, width_mm=70)

    kept = keep_from_pack(placement, wide)

    assert kept.from_pack is not None
    assert (kept.from_pack.anchor, kept.from_pack.build) == ("supervisor", SHA[:16])
    assert kept.from_pack.digest == placement_digest(wide)


# --- отпечаток записи пака и ответы (15.17.10, 15.17.14) ---


def test__pack_digest__of_the_record_not_of_the_layout() -> None:
    slot = _slot()
    moved = _slot(
        placements=(("topic_application", AnchorPlace("supervisor", align=DateMarkAlign.right, width_mm=30)),)
    )
    to_mm = _slot(placements=(("topic_application", SignatureDefaultPlacement(1, 167, 177, 28)),))

    assert pack_digest(slot, "topic_application") == pack_digest(_slot(), "topic_application")
    assert pack_digest(slot, "topic_application") != pack_digest(moved, "topic_application")
    assert pack_digest(slot, "topic_application") != pack_digest(to_mm, "topic_application")


def test__pack_digest__mm_record_unchanged_by_the_anchor_support() -> None:
    # Отпечаток места в мм тот же, что до якорей: R26 не видит изменения у прежних версий пака.
    slot = _slot(placements=())

    assert pack_digest(slot, "report") == place_digest(1, 110, 130, 40, ())


def test__anchor_ref__found_missing_unknown() -> None:
    slot = _slot()

    assert anchor_ref(slot, "topic_application", _src(RU_LINE)).state is AnchorState.found  # type: ignore[union-attr]
    assert anchor_ref(slot, "topic_application", _src()).state is AnchorState.missing  # type: ignore[union-attr]
    assert anchor_ref(slot, "topic_application", NO_ANCHORS).state is AnchorState.unknown  # type: ignore[union-attr]
    own = SourceAnchors(own_pdf=True)
    assert anchor_ref(slot, "topic_application", own).state is AnchorState.unknown  # type: ignore[union-attr]
    assert anchor_ref(slot, "report", _src(RU_LINE)) is None  # место в мм


def test__place_source__by_origin_and_mark() -> None:
    anchored = pack_placement(_slot(), "topic_application", None, "2026.1.5", _src(RU_LINE))
    assert anchored is not None
    plain = SignaturePlacement(enabled=False, page=1, x_mm=110, y_mm=130, width_mm=40)

    assert place_source(anchored, PlacementOrigin.pack) is PlaceSource.anchor
    assert place_source(plain, PlacementOrigin.seed) is PlaceSource.mm
    assert place_source(anchored, PlacementOrigin.manual) is None


def test__default_anchor__entry_for_documents_without_own_record() -> None:
    default = AnchorPlace("supervisor", width_mm=28, fallback=GENERAL)
    slot = _slot(default_anchor=default)

    assert slot.entry_for("report") == default
    assert slot.place_for("report") == GENERAL
    assert slot.uses_anchors("report")
