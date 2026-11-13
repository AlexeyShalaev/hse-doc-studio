"""Метки даты подписания в видимом слое (docs/design/signing-route.md, 14.3): когда рисуются и что меняют."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat, SignedAtSource, SignMode
from hse_doc_studio.core.signatures.stamps import date_mark_text, stamps_digest, stamps_for_doc
from hse_doc_studio.core.value_objects import (
    DateMark,
    SignaturePlacement,
    SignatureSlot,
    SignaturesState,
    SignedAt,
    SkippedSlot,
)

ROOT = Path("/projects/p1")
DAY = DateMark(id="d1", page=2, x_mm=120, y_mm=250, width_mm=8, height_mm=5, format=DateMarkFormat.day)
MONTH = DateMark(
    id="d2",
    page=2,
    x_mm=132,
    y_mm=250,
    width_mm=22,
    height_mm=5,
    format=DateMarkFormat.month_word,
    align=DateMarkAlign.left,
)
YEAR = DateMark(id="d3", page=2, x_mm=160, y_mm=250, width_mm=6, height_mm=5, format=DateMarkFormat.year_short)
# Научрук согласовал 12.11 в 23:30 UTC: по Москве это уже 13 ноября.
APPROVED = SignedAt(at="2026-11-12T23:30:00+00:00", source=SignedAtSource.approval, token="build:abc")


def _state(
    *, signed_at: SignedAt | None = APPROVED, enabled: bool = True, marks: tuple[DateMark, ...] = (DAY, MONTH, YEAR)
) -> SignaturesState:
    return SignaturesState(
        slots={"supervisor": SignatureSlot(png_path="signatures/sup.png", natural_width_px=100, natural_height_px=40)},
        placements={
            "proposal": {
                "supervisor": SignaturePlacement(
                    enabled=enabled, page=1, x_mm=10, y_mm=20, width_mm=40, dates=marks, signed_at=signed_at
                )
            }
        },
    )


def _stamps(state: SignaturesState, lang: str = "ru", **kwargs: object) -> list:
    return stamps_for_doc(state, "proposal", ROOT, lang, png_exists=lambda _p: True, **kwargs)  # type: ignore[arg-type]


def test__signed_slot__picture_then_three_date_marks_with_moscow_day() -> None:
    picture, *marks = _stamps(_state())

    assert not picture.is_date
    assert [(m.page, m.x_mm, m.text, m.height_mm, m.align, m.is_date) for m in marks] == [
        (2, 120, "13", 5, "center", True),
        (2, 132, "ноября", 5, "left", True),
        (2, 160, "26", 5, "center", True),
    ]
    assert {m.slot_id for m in marks} == {"supervisor"}


def test__english_document__month_in_english() -> None:
    texts = [s.text for s in _stamps(_state(), "en") if s.is_date]

    assert texts == ["13", "November", "26"]


def test__no_signed_at__no_date_marks_and_text_is_none() -> None:
    state = _state(signed_at=None)

    assert [s for s in _stamps(state) if s.is_date] == []
    assert date_mark_text(state, "proposal", "supervisor", DAY, "ru") is None


@pytest.mark.parametrize(
    "hidden",
    [
        {"withheld": {"proposal": frozenset({"supervisor"})}},
        {"skipped": {"proposal": {"supervisor": SkippedSlot("final", "r1", 1, "2026-11-13T10:00:00Z")}}},
    ],
    ids=["withheld", "skipped"],
)
def test__withheld_or_skipped_slot__neither_mark_nor_dates(hidden: dict[str, object]) -> None:
    state = replace(_state(), **hidden)  # type: ignore[arg-type]

    assert _stamps(state) == []
    assert date_mark_text(state, "proposal", "supervisor", DAY, "ru") is None


def test__skipped_but_mark_kept_in_signed_pdf__dates_stay_with_it() -> None:
    skip = SkippedSlot("final", "r1", 1, "2026-11-13T10:00:00Z", keep_mark=True)
    state = replace(_state(), skipped={"proposal": {"supervisor": skip}})

    assert len([s for s in _stamps(state) if s.is_date]) == 3


def test__signature_not_placed__dates_drawn_alone() -> None:
    """PAdES без видимой метки или выключенное место: дата всё равно ставится (14.3)."""
    stamps = _stamps(_state(enabled=False))

    assert [s.text for s in stamps] == ["13", "ноября", "26"]


def test__plate_slot__dates_follow_the_plate() -> None:
    state = _state()
    plate = SignatureSlot(None, None, None, sign_mode=SignMode.detached_text)
    state = replace(state, slots={"supervisor": plate})

    plate_stamp, *marks = _stamps(state)

    assert plate_stamp.text is not None
    assert not plate_stamp.is_date
    assert len(marks) == 3


def test__slot_filter__dates_of_other_slots_left_out() -> None:
    assert _stamps(_state(), slot_ids=["author"]) == []
    assert len(_stamps(_state(), slot_ids=["supervisor"])) == 4


def test__fingerprint__changes_with_the_mark_its_box_alignment_and_the_day() -> None:
    base = stamps_digest(_stamps(_state()), ROOT)
    moved = replace(MONTH, x_mm=133)
    aligned = replace(MONTH, align=DateMarkAlign.right)
    taller = replace(MONTH, height_mm=6)
    other_day = SignedAt(at="2026-11-14", source=SignedAtSource.manual)

    variants = [
        _state(marks=(DAY, MONTH)),
        _state(marks=(DAY, moved, YEAR)),
        _state(marks=(DAY, aligned, YEAR)),
        _state(marks=(DAY, taller, YEAR)),
        _state(signed_at=other_day),
    ]

    digests = {stamps_digest(_stamps(state), ROOT) for state in variants}
    assert base not in digests
    assert len(digests) == len(variants)


def test__fingerprint__same_moment_from_approval_or_manual_same_day__same_layer() -> None:
    """В слой входит напечатанный текст, а не источник даты: тот же день не делает фиксацию устаревшей."""
    manual = SignedAt(at="2026-11-13", source=SignedAtSource.manual)

    assert stamps_digest(_stamps(_state()), ROOT) == stamps_digest(_stamps(_state(signed_at=manual)), ROOT)


def test__fingerprint__without_dates__same_as_before_date_marks() -> None:
    """Отпечаток слоя без меток даты не меняется от появления полей метки: прежние фиксации не устаревают."""
    no_marks = _stamps(_state(marks=()))
    empty_marks = _stamps(_state(signed_at=None))

    assert stamps_digest(no_marks, ROOT) == stamps_digest(empty_marks, ROOT)
    assert "height_mm" not in repr(no_marks)
