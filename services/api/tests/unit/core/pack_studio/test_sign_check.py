"""Проверка мест подписей (pack-studio-mcp.md, 4.4) на страницах без PDF: правила по одному."""

from __future__ import annotations

from hse_doc_studio.core.pack_studio.sign_check import (
    Glyph,
    Line,
    LineSource,
    PageLayout,
    Place,
    PlaceKind,
    Rect,
    SlotCheck,
    check_places,
    label_words,
    on_line,
    sign_rect,
    underscore_lines,
    words_of,
)


def _glyphs(text: str, x: float, baseline: float, size: float = 2.5) -> list[Glyph]:
    return [Glyph(ch, Rect(x + i * size, baseline - 3.5, x + (i + 1) * size, baseline)) for i, ch in enumerate(text)]


def _page(*lines: Line, text: str = "", text_at: tuple[float, float] = (25, 120)) -> PageLayout:
    glyphs = _glyphs(text, *text_at) if text else []
    words = words_of(glyphs)
    return PageLayout(1, 210, 297, tuple(glyphs), words, (*lines, *underscore_lines(words)))


_LINE = Line(120, 170, 150, LineSource.drawing)


def _place(slot: str, x: float, y: float, w: float = 40, page: int = 1, **extra: object) -> Place:
    return Place(slot, slot, page, sign_rect(x, y, w), **extra)  # type: ignore[arg-type]


def _codes(check: SlotCheck) -> list[str]:
    return [f.code.value for f in check.findings]


def test__on_line__box_over_the_line_and_beside_it() -> None:
    assert on_line(sign_rect(125, 140, 40), _LINE)
    assert not on_line(sign_rect(40, 140, 40), _LINE)
    assert not on_line(sign_rect(125, 100, 40), _LINE)


def test__good_place__no_findings() -> None:
    (check,) = check_places([_place("author", 125, 140)], [], {1: _page(_LINE)}, 1, {0: 0.01})
    assert check.findings == ()
    assert check.status is None


def test__missing_out_of_range_and_off_sheet() -> None:
    checks = check_places(
        [_place("a", 125, 140, page=3), _place("b", 190, 140)], [("c", "C")], {1: _page(_LINE)}, 2, {}
    )
    by = {c.slot: _codes(c) for c in checks}
    assert by["c"] == ["no_place"]
    assert by["a"] == ["page_out_of_range"]
    assert "outside_page" in by["b"]


def test__near_edge_and_busy_area() -> None:
    edge, busy = check_places([_place("a", 2, 140), _place("b", 125, 140)], [], {1: _page(_LINE)}, 1, {0: 0.0, 1: 0.2})
    assert "near_edge" in _codes(edge)
    assert _codes(busy) == ["busy_area"]


def test__overlaps_text_but_captions_and_underscores_are_fine() -> None:
    page = _page(_LINE, text="Фамилия (подпись) ____", text_at=(120, 150))
    (check,) = check_places([_place("a", 118, 140, 50)], [], {1: page}, 1, {})
    assert _codes(check)[0] == "overlaps_text"
    assert "Фамилия" in str(check.findings[0].data["text"])
    assert "подпись" not in str(check.findings[0].data["text"])


def test__overlapping_places_and_date_marks() -> None:
    date = Place("b", "b", 1, Rect(130, 145, 150, 150), kind=PlaceKind.date)
    checks = check_places([_place("a", 125, 140), _place("b", 130, 141), date], [], {1: _page(_LINE)}, 1, {})
    by = {c.slot: _codes(c) for c in checks}
    assert "overlaps_place" in by["a"]
    assert "overlaps_place" in by["b.date"]


def test__far_box__suggested_on_the_labelled_line() -> None:
    other = Line(30, 80, 200, LineSource.drawing)
    page = _page(_LINE, other, text="Автор", text_at=(100, 150))
    place = _place("author", 40, 100, words=label_words("Автор", "Author"))

    (check,) = check_places([place], [], {1: page}, 1, {})

    assert _codes(check) == ["far_from_line"]
    assert check.line == _LINE
    assert check.suggested is not None
    assert on_line(check.suggested, _LINE)
    assert check.suggested.cx == 145


def test__anchor_of_the_slot_wins_even_on_another_page() -> None:
    anchor = Line(60, 110, 250, LineSource.anchor, anchor="supervisor")
    page2 = PageLayout(2, 210, 297)
    place = _place("supervisor", 125, 140)

    (check,) = check_places([place], [], {1: _page(_LINE), 2: page2}, 2, {}, {"supervisor": (2, anchor)})

    assert _codes(check) == ["far_from_line", "anchor_available"]
    assert check.bind_anchor is True
    assert check.line_page == 2
    assert check.suggested is not None


def test__place_on_its_anchor__no_hint_to_bind() -> None:
    anchor = Line(120, 170, 150, LineSource.anchor, anchor="a")
    (check,) = check_places([_place("a", 125, 140, origin="anchor")], [], {1: _page()}, 1, {}, {"a": (1, anchor)})
    assert check.findings == ()
    assert check.bind_anchor is False


def test__underscores__become_a_line_under_the_run() -> None:
    words = words_of(_glyphs("Подпись ______ ", 25, 120))
    (line,) = underscore_lines(words)
    assert line.source is LineSource.underscores
    assert line.y == 120
    assert line.x0 > 40
