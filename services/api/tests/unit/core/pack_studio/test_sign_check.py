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
    Word,
    check_places,
    is_date_blank,
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


def _words(*runs: tuple[str, float, float]) -> tuple[list[Glyph], tuple[Word, ...]]:
    glyphs = [g for text, x, baseline in runs for g in _glyphs(text, x, baseline)]
    return glyphs, words_of(glyphs)


def test__is_date_blank__month_gap_between_the_day_and_the_year() -> None:
    # «« __ » ______ 2026 г.»: пропуск месяца 40..70 мм, слева «»», справа год.
    _, words = _words(("«__»", 30, 150), ("2026 г.", 72, 150))
    month = Line(40, 70, 150, LineSource.drawing)
    sign = Line(40, 70, 130, LineSource.drawing)

    assert is_date_blank(month, words)
    assert not is_date_blank(sign, words)
    assert not is_date_blank(Line(110, 160, 150, LineSource.drawing), words)


def test__far_box__date_blank_of_the_column_is_not_the_signature_line() -> None:
    # Колонка «Научный руководитель»: строка подписи на 130 мм, ниже строка даты с пропуском месяца на 150 мм.
    # Пропуск ближе к рамке, но подпись не на нём.
    glyphs, words = _words(("Научный руководитель", 30, 110), ("«__»", 20, 150), ("2026 г.", 72, 150))
    sign = Line(30, 90, 130, LineSource.drawing)
    month = Line(31, 70, 150, LineSource.drawing)
    page = PageLayout(1, 210, 297, tuple(glyphs), words, (sign, month))
    place = _place("supervisor", 30, 160, words=label_words("Научный руководитель", "Supervisor"))

    (check,) = check_places([place], [], {1: page}, 1, {})

    assert check.line == sign
    assert check.suggested is not None
    assert on_line(check.suggested, sign)


def test__far_box__suggestion_may_cover_only_small_caption_text() -> None:
    # Над линией 120..170 мм на 150 мм мелкая подпись строки выше («И.О. Фамилия», высота 2 мм) на 141..143 мм:
    # обе рамки предложения её задевают, но проверка считает это замечанием, а не ошибкой.
    caption = [Glyph(ch, Rect(130 + i * 1.5, 141, 131.5 + i * 1.5, 143)) for i, ch in enumerate("ИОФамилия")]
    page = PageLayout(1, 210, 297, tuple(caption), words_of(caption), (_LINE,))
    place = _place("author", 40, 100)

    (check,) = check_places([place], [], {1: page}, 1, {})
    (after,) = check_places([_place("author", *_xy(check.suggested))], [], {1: page}, 1, {})

    assert check.line == _LINE
    assert check.suggested is not None
    assert on_line(check.suggested, _LINE)
    assert after.status is not None
    assert after.status.value == "warning"


def _xy(rect: Rect | None) -> tuple[float, float, float]:
    assert rect is not None
    return rect.x0, rect.y0, rect.width


def test__slot_line_not_printed_in_this_build__a_hint_not_an_error() -> None:
    # Место консультанта на якоре, а строку консультанта шаблон без консультанта не печатает: места нет по замыслу.
    checks = check_places([], [("supervisor", "S")], {}, 1, {}, absent=[("co_supervisor", "C", "co_supervisor")])

    by = {c.slot: c for c in checks}
    assert _codes(by["supervisor"]) == ["no_place"]
    assert by["supervisor"].status is not None
    assert by["supervisor"].status.value == "error"
    assert _codes(by["co_supervisor"]) == ["anchor_missing"]
    assert by["co_supervisor"].findings[0].data == {"anchor": "co_supervisor"}
    assert by["co_supervisor"].status is None
