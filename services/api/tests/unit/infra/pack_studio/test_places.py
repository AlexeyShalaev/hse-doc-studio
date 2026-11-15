"""Места подписей и метки даты в `version.yaml` (template-studio.md, 5.6, срез T9): модель и точечные правки."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from hse_doc_studio.core.catalog import AnchorDate, AnchorPlace, SignatureDefaultPlacement
from hse_doc_studio.core.enums import AnchorState, DateMarkAlign, DateMarkFormat
from hse_doc_studio.core.pack_studio.places import (
    FrameKind,
    MarkBox,
    PlaceBox,
    PlaceEditError,
    PlaceOp,
    PlaceOpKind,
)
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors
from hse_doc_studio.infra.pack_studio.places import PackPlacesEditor
from hse_doc_studio.infra.template.yaml_template_repository import parse_signature_slot

_REPO = Path(__file__).resolve().parents[6]
_PACKS = _REPO / "packs"

TEXT = """\
id: "2026.1.2"
documents:
  - application
  - report
  - shared_report

signatures:
  slots:
    # Автор подписывает заявление и отчёт.
    - id: author
      label:             { ru: Автор, en: Author }
      applies_to:        [application, report]
      default_placement: { page: 1, x_mm: 160, y_mm: 208, width_mm: 30 }
      placements:
        # Заявление: правый край рамки у конца линии.
        application: { anchor: author, align: right, dy_mm: -11, width_mm: 30, page: 1, x_mm: 165, y_mm: 201 }
      default_dates:
        report:
          - { page: 1, x_mm: 81, y_mm: 156, width_mm: 7, height_mm: 5, format: day }
          - { anchor: author.month_word }

    - id: supervisor
      label:             { ru: Руководитель, en: Supervisor }
      applies_to:        [application, report, shared_report]
      per_author: false
      default_placement: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 }

    - id: consultant
      label:             { ru: Консультант, en: Consultant }
      applies_to:        [application]
      # Строка печатается, только если консультант указан.
      default_placement: { anchor: consultant, align: right, width_mm: 28, page: 1, x_mm: 168, y_mm: 216 }
"""

ANCHORS = BuildAnchors(
    pdf_sha256="a" * 64,
    anchors=(
        BuildAnchor("author", AnchorKind.sign, 1, 135.0, 212.0, 30.0),
        BuildAnchor("supervisor", AnchorKind.sign, 1, 60.0, 180.0, 40.0),
        BuildAnchor("author.month_word", AnchorKind.date, 1, 40.0, 160.0, 25.0),
        BuildAnchor("author.day", AnchorKind.date, 1, 30.0, 160.0, 8.0),
    ),
)

EDITOR = PackPlacesEditor()


def _slot(text: str, slot_id: str) -> dict[str, object]:
    slots = yaml.safe_load(text)["signatures"]["slots"]
    return next(s for s in slots if s["id"] == slot_id)


def _apply(*ops: PlaceOp, document: str | None = "application", anchors: BuildAnchors | None = ANCHORS) -> str:
    return EDITOR.apply(TEXT, ops, document=document, anchors=anchors)


def _changed(new: str) -> list[str]:
    old_lines = TEXT.splitlines()
    new_lines = new.splitlines()
    return [line for line in new_lines if line not in old_lines] + [
        f"-{line}" for line in old_lines if line not in new_lines
    ]


# ── модель ──────────────────────────────────────────────────────────────────


def test__describe__catalog_with_entries_and_frames_of_the_build_document() -> None:
    places = EDITOR.describe(TEXT, document="application", anchors=ANCHORS)

    assert places.documents == ("application", "report", "shared_report")
    assert [s.id for s in places.slots] == ["author", "supervisor", "consultant"]
    assert places.anchors_known is True
    assert places.sign_anchors == ("author", "supervisor")
    assert places.date_anchors == ("author.month_word", "author.day")
    author = places.slots[0]
    assert author.document is not None
    assert author.document.kind is FrameKind.place
    assert isinstance(author.document.entry, AnchorPlace)
    # Правый край рамки у конца линии: 135 + 30 - 30 = 135, верх 212 - 11.
    assert author.document.box == SignatureDefaultPlacement(page=1, x_mm=135.0, y_mm=201.0, width_mm=30.0)
    assert author.document.anchor is not None
    assert author.document.anchor.state is AnchorState.found
    supervisor = places.slots[1]
    assert supervisor.document is not None
    assert supervisor.document.kind is FrameKind.default
    assert supervisor.document.box == SignatureDefaultPlacement(page=1, x_mm=110.0, y_mm=130.0, width_mm=40.0)
    consultant = places.slots[2]
    assert consultant.document is not None
    assert consultant.document.box is None
    assert consultant.document.anchor is not None
    assert consultant.document.anchor.state is AnchorState.missing


def test__describe__dates_keep_yaml_indices_and_anchor_marks_resolve_on_lines() -> None:
    places = EDITOR.describe(TEXT, document="report", anchors=ANCHORS)

    author = places.slots[0]
    assert author.document is not None
    dates = author.document.dates
    assert [d.index for d in dates] == [0, 1]
    assert dates[0].anchor is None
    assert isinstance(dates[1].entry, AnchorDate)
    assert dates[1].box is not None
    assert (dates[1].box.x_mm, dates[1].box.y_mm, dates[1].box.width_mm) == (40.0, 155.0, 25.0)
    # Консультант к отчёту не относится: рамок нет.
    assert places.slots[2].document is None


def test__describe__without_anchors_uses_fallbacks_and_marks_them_unknown() -> None:
    places = EDITOR.describe(TEXT, document="application", anchors=None)

    author = places.slots[0]
    assert author.document is not None
    assert author.document.box == SignatureDefaultPlacement(page=1, x_mm=165.0, y_mm=201.0, width_mm=30.0)
    assert author.document.anchor is not None
    assert author.document.anchor.state is AnchorState.unknown
    assert places.anchors_known is False
    assert places.sign_anchors == ()


def test__describe__without_a_build_has_no_frames() -> None:
    places = EDITOR.describe(TEXT, document=None, anchors=None)

    assert all(slot.document is None for slot in places.slots)
    assert places.slots[0].default_set is True
    assert dict(places.slots[0].places)["application"] == AnchorPlace(
        anchor="author",
        align=DateMarkAlign.right,
        dy_mm=-11.0,
        width_mm=30.0,
        fallback=SignatureDefaultPlacement(page=1, x_mm=165.0, y_mm=201.0, width_mm=30.0),
    )


@pytest.mark.parametrize("manifest", sorted(_PACKS.glob("*/templates/*/versions/*/version.yaml")), ids=str)
def test__describe__every_pack_version_of_the_repo_reads(manifest: Path) -> None:
    text = manifest.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    places = EDITOR.describe(text, document=None, anchors=None)

    assert len(places.slots) == len(raw.get("signatures", {}).get("slots", []))


# ── места ───────────────────────────────────────────────────────────────────


def test__set_place__anchored_place_moves_relative_to_its_line_and_keeps_the_fallback() -> None:
    new = _apply(PlaceOp(PlaceOpKind.set_place, "author", "application", box=PlaceBox(1, 130.4, 199.6, 31)))

    entry = "{ anchor: author, align: right, %s, page: 1, x_mm: 165, y_mm: 201 }"
    assert _changed(new) == [
        "        application: " + entry % "dx_mm: -4, dy_mm: -12, width_mm: 31",
        "-        application: " + entry % "dy_mm: -11, width_mm: 30",
    ]
    # Комментарий над записью и выравнивание соседей не тронуты.
    assert "        # Заявление: правый край рамки у конца линии." in new


def test__set_place__without_anchors_the_fallback_moves() -> None:
    new = _apply(PlaceOp(PlaceOpKind.set_place, "author", "application", box=PlaceBox(1, 150, 190, 30)), anchors=None)

    entry = _slot(new, "author")["placements"]["application"]  # type: ignore[index]
    assert entry == {
        "anchor": "author",
        "align": "right",
        "dy_mm": -11,
        "width_mm": 30,
        "page": 1,
        "x_mm": 150,
        "y_mm": 190,
    }


def test__set_place__new_place_of_a_document_lands_on_the_template_line() -> None:
    new = _apply(PlaceOp(PlaceOpKind.set_place, "supervisor", "application", box=PlaceBox(1, 62.2, 168.7, 40)))

    slot = _slot(new, "supervisor")
    assert slot["placements"] == {
        "application": {
            "anchor": "supervisor",
            "align": "left",
            "dx_mm": 2,
            "dy_mm": -11,
            "width_mm": 40,
            "page": 1,
            "x_mm": 62,
            "y_mm": 169,
        }
    }
    assert "      placements:\n        application: { anchor: supervisor, align: left," in new
    assert parse_signature_slot(slot).entry_for("application") == AnchorPlace(
        anchor="supervisor",
        align=DateMarkAlign.left,
        dx_mm=2.0,
        dy_mm=-11.0,
        width_mm=40.0,
        fallback=SignatureDefaultPlacement(page=1, x_mm=62.0, y_mm=169.0, width_mm=40.0),
    )


def test__set_place__new_place_without_a_line_is_in_mm() -> None:
    new = _apply(PlaceOp(PlaceOpKind.set_place, "supervisor", "report", box=PlaceBox(2, 20.4, 30.5, 9)), anchors=None)

    assert _slot(new, "supervisor")["placements"] == {"report": {"page": 2, "x_mm": 20, "y_mm": 30, "width_mm": 10}}


def test__set_place__default_placement_in_mm() -> None:
    new = _apply(PlaceOp(PlaceOpKind.set_place, "supervisor", None, box=PlaceBox(1, 100, 120, 45)))

    assert _changed(new) == [
        "      default_placement: { page: 1, x_mm: 100, y_mm: 120, width_mm: 45 }",
        "-      default_placement: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 }",
    ]


def test__set_place__slot_not_applicable_to_the_document_is_refused() -> None:
    with pytest.raises(PlaceEditError, match="does not apply"):
        _apply(PlaceOp(PlaceOpKind.set_place, "consultant", "report", box=PlaceBox(1, 10, 10, 30)))


def test__set_place__unknown_slot_is_refused() -> None:
    with pytest.raises(PlaceEditError, match="not in the catalog"):
        _apply(PlaceOp(PlaceOpKind.set_place, "dean", "report", box=PlaceBox(1, 10, 10, 30)))


def test__set_place__box_is_clamped_to_the_sheet() -> None:
    new = _apply(PlaceOp(PlaceOpKind.set_place, "supervisor", "report", box=PlaceBox(1, 195, 295, 40)), anchors=None)

    assert _slot(new, "supervisor")["placements"] == {"report": {"page": 1, "x_mm": 170, "y_mm": 287, "width_mm": 40}}


def test__remove_place__last_entry_takes_the_placements_key_and_its_comment() -> None:
    new = _apply(PlaceOp(PlaceOpKind.remove_place, "author", "application"))

    assert "placements" not in _slot(new, "author")
    assert "Заявление: правый край" not in new
    assert "default_dates:" in new


def test__remove_place__missing_entry_is_refused() -> None:
    with pytest.raises(PlaceEditError, match="no place of its own"):
        _apply(PlaceOp(PlaceOpKind.remove_place, "supervisor", "report"))


def test__make_default__moves_the_document_entry_to_default_placement() -> None:
    new = _apply(PlaceOp(PlaceOpKind.make_default, "author", "application"))

    slot = _slot(new, "author")
    assert slot["default_placement"] == {
        "anchor": "author",
        "align": "right",
        "dy_mm": -11,
        "width_mm": 30,
        "page": 1,
        "x_mm": 165,
        "y_mm": 201,
    }
    assert "placements" not in slot


def test__make_default__anchored_entry_without_fallback_gets_the_frame_of_the_build() -> None:
    first = _apply(PlaceOp(PlaceOpKind.set_place, "supervisor", "application", box=PlaceBox(1, 62, 169, 40)))
    bare = first.replace(", page: 1, x_mm: 62, y_mm: 169 }", " }")

    new = EDITOR.apply(
        bare, [PlaceOp(PlaceOpKind.make_default, "supervisor", "application")], document="application", anchors=ANCHORS
    )

    default = _slot(new, "supervisor")["default_placement"]
    assert default == {
        "anchor": "supervisor",
        "align": "left",
        "dx_mm": 2,
        "dy_mm": -11,
        "width_mm": 40,
        "page": 1,
        "x_mm": 62,
        "y_mm": 169,
    }


def test__bind_and_unbind__place_switches_between_the_line_and_mm() -> None:
    bound = _apply(PlaceOp(PlaceOpKind.bind_anchor, "supervisor", "application"))

    entry = _slot(bound, "supervisor")["placements"]["application"]  # type: ignore[index]
    assert entry == {
        "anchor": "supervisor",
        "align": "left",
        "dx_mm": 50,
        "dy_mm": -50,
        "width_mm": 40,
        "page": 1,
        "x_mm": 110,
        "y_mm": 130,
    }

    unbound = EDITOR.apply(
        bound,
        [PlaceOp(PlaceOpKind.unbind_anchor, "supervisor", "application")],
        document="application",
        anchors=ANCHORS,
    )

    assert _slot(unbound, "supervisor")["placements"] == {
        "application": {"page": 1, "x_mm": 110, "y_mm": 130, "width_mm": 40}
    }


def test__bind__without_the_line_in_the_build_is_refused() -> None:
    with pytest.raises(PlaceEditError, match="no template line"):
        _apply(PlaceOp(PlaceOpKind.bind_anchor, "consultant", "application"))


def test__unbind__place_in_mm_is_refused() -> None:
    with pytest.raises(PlaceEditError, match="not on a template line"):
        _apply(PlaceOp(PlaceOpKind.unbind_anchor, "supervisor", "report"))


# ── метки даты ──────────────────────────────────────────────────────────────


def test__add_date__first_mark_creates_default_dates_in_block_style() -> None:
    mark = MarkBox(1, 100.2, 140, 28, 6, DateMarkFormat.date_numeric)

    new = _apply(PlaceOp(PlaceOpKind.add_date, "supervisor", "report", mark=mark), anchors=None)

    assert (
        "      default_dates:\n        report:\n"
        "          - { page: 1, x_mm: 100, y_mm: 140, width_mm: 28, height_mm: 6, format: date_numeric }\n"
    ) in new


def test__add_date__on_a_date_line_of_the_build() -> None:
    new = _apply(PlaceOp(PlaceOpKind.add_date, "author", "report", anchor="author.day"), document="report")

    assert _slot(new, "author")["default_dates"]["report"][-1] == {"anchor": "author.day"}  # type: ignore[index]


def test__add_date__line_missing_in_the_build_is_refused() -> None:
    with pytest.raises(PlaceEditError, match="no date line"):
        _apply(PlaceOp(PlaceOpKind.add_date, "author", "report", anchor="author.year"), document="report")


def test__add_date__ninth_mark_is_refused() -> None:
    mark = MarkBox(1, 10, 10, 10, 5, DateMarkFormat.day)
    text = TEXT
    for _ in range(6):
        text = EDITOR.apply(
            text, [PlaceOp(PlaceOpKind.add_date, "author", "report", mark=mark)], document="report", anchors=None
        )

    with pytest.raises(PlaceEditError, match="already has 8"):
        EDITOR.apply(
            text, [PlaceOp(PlaceOpKind.add_date, "author", "report", mark=mark)], document="report", anchors=None
        )


def test__set_date__mark_in_mm_changes_in_place() -> None:
    mark = MarkBox(1, 82.4, 157, 8, 5, DateMarkFormat.day, DateMarkAlign.right)

    new = _apply(PlaceOp(PlaceOpKind.set_date, "author", "report", index=0, mark=mark), document="report")

    assert "          - { page: 1, x_mm: 82, y_mm: 157, width_mm: 8, height_mm: 5, format: day, align: right }" in new


def test__set_date__anchored_mark_moves_relative_to_its_line() -> None:
    mark = MarkBox(1, 42.3, 152, 25, 5, DateMarkFormat.month_word)

    new = _apply(PlaceOp(PlaceOpKind.set_date, "author", "report", index=1, mark=mark), document="report")

    assert _slot(new, "author")["default_dates"]["report"][1] == {  # type: ignore[index]
        "anchor": "author.month_word",
        "dx_mm": 2,
        "dy_mm": -8,
    }


def test__set_date__unchanged_anchored_mark_stays_bare() -> None:
    mark = MarkBox(1, 40, 155, 25, 5, DateMarkFormat.month_word)

    new = _apply(PlaceOp(PlaceOpKind.set_date, "author", "report", index=1, mark=mark), document="report")

    assert new == TEXT


def test__remove_date__last_marks_take_default_dates_away() -> None:
    once = _apply(PlaceOp(PlaceOpKind.remove_date, "author", "report", index=1), document="report")
    assert len(_slot(once, "author")["default_dates"]["report"]) == 1  # type: ignore[index]

    twice = EDITOR.apply(
        once, [PlaceOp(PlaceOpKind.remove_date, "author", "report", index=0)], document="report", anchors=None
    )

    assert "default_dates" not in _slot(twice, "author")


def test__remove_date__index_out_of_range_is_refused() -> None:
    with pytest.raises(PlaceEditError, match="no date mark 5"):
        _apply(PlaceOp(PlaceOpKind.remove_date, "author", "report", index=5), document="report")


def test__apply__anchors_of_another_document_are_not_used() -> None:
    # Сборка заявления, правка отчёта: якорей отчёта нет, новое место в мм.
    new = _apply(PlaceOp(PlaceOpKind.set_place, "supervisor", "report", box=PlaceBox(1, 62, 169, 40)))

    assert _slot(new, "supervisor")["placements"] == {"report": {"page": 1, "x_mm": 62, "y_mm": 169, "width_mm": 40}}


def test__apply__real_pack_place_edit_touches_one_line() -> None:
    manifest = _PACKS / "hse-cs-sse/templates/coursework/versions/2026.1.6/version.yaml"
    text = manifest.read_text(encoding="utf-8")

    new = EDITOR.apply(
        text,
        [PlaceOp(PlaceOpKind.set_place, "supervisor", "topic_application", box=PlaceBox(1, 150, 170, 28))],
        document="topic_application",
        anchors=None,
    )

    diff = [(a, b) for a, b in zip(text.splitlines(), new.splitlines(), strict=True) if a != b]
    entry = "        topic_application: { anchor: supervisor, align: right, width_mm: 28, page: 1, %s }"
    assert diff == [(entry % "x_mm: 168, y_mm: 177", entry % "x_mm: 150, y_mm: 170")]
