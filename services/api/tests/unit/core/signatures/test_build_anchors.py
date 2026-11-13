"""Якоря сборки: разбор файла позиций TeX и `anchors.json` (signing-route.md, 15.17.4)."""

from __future__ import annotations

import json

import pytest
from hse_doc_studio.core.signatures.anchors import (
    MAX_ANCHORS,
    MAX_POSITIONS_BYTES,
    AnchorKind,
    AnchorProblem,
    BuildAnchor,
    BuildAnchors,
    PdfPage,
    PositionsFormatError,
    decode_anchors,
    encode_anchors,
    is_anchor_id,
    parse_positions,
)

SHA = "a" * 64
A4 = PdfPage(width_mm=210.0, height_mm=297.0)
# A4 в sp, как его пишет `\number\paperwidth` (595.30026pt x 845.04684pt).
A4_HEADER = "hsepos 1 39158276 55380990"


def _sp(mm: float) -> int:
    return round(mm / 25.4 * 72.27 * 65536)


def _line(kind: str, name: str, part: str, page: int, x_mm: float, from_bottom_mm: float, width_mm: float) -> str:
    return f"{kind} {name} {part} {page} {_sp(x_mm)} {_sp(from_bottom_mm)} {_sp(width_mm)}"


def _file(*lines: str, header: str = A4_HEADER) -> bytes:
    return ("\n".join((header, *lines)) + "\n").encode("utf-8")


def test__parse__sign_and_date__mm_from_top_left_rounded() -> None:
    raw = _file(
        _line("sign", "supervisor", "-", 1, 169.5, 297 - 186.9, 25.5),
        _line("date", "supervisor", "day", 2, 36.04, 297 - 40.0, 0),
    )

    anchors = parse_positions(raw, [A4, A4], SHA)

    assert anchors.anchors == (
        BuildAnchor("supervisor", AnchorKind.sign, 1, 169.5, 186.9, 25.5),
        BuildAnchor("supervisor.day", AnchorKind.date, 2, 36.0, 40.0, 0.0),
    )
    assert anchors.problems == ()
    assert anchors.duplicates == ()
    assert anchors.build == SHA[:16]
    assert anchors.of(SHA)
    assert not anchors.of("b" * 64)
    assert not anchors.of(None)


def test__parse__real_xelatex_output__positions_as_measured() -> None:
    # Строки из настоящей сборки XeLaTeX (TL2024): A4, поля 30 мм, абзацный отступ.
    raw = _file(
        "sign supervisor - 1 6773687 49914927 7458719",
        "sign academic_supervisor - 1 5987255 48971212 29980786",
        "date supervisor day 2 34496578 50865199 0",
    )

    anchors = parse_positions(raw, [A4, A4], SHA)

    supervisor = anchors.get("supervisor")
    assert supervisor is not None
    assert (supervisor.page, supervisor.x_mm, supervisor.y_mm, supervisor.width_mm) == (1, 36.3, 29.3, 40.0)
    assert anchors.get("supervisor.day") is not None
    assert anchors.get("nobody") is None


def test__parse__height_from_pdf_not_paperheight() -> None:
    # Бумага в заголовке 297 мм, у PDF 297,6: расхождение меньше 1 мм, y считается от высоты PDF.
    raw = _file(_line("sign", "author", "-", 1, 10, 100, 10))

    anchors = parse_positions(raw, [PdfPage(210.0, 297.6)], SHA)

    assert anchors.anchors[0].y_mm == 197.6


def test__parse__page_size_mismatch__anchors_of_that_page_dropped() -> None:
    raw = _file(
        _line("sign", "author", "-", 1, 10, 100, 10),
        _line("sign", "supervisor", "-", 2, 10, 100, 10),
    )

    anchors = parse_positions(raw, [A4, PdfPage(297.0, 420.0)], SHA)

    assert [a.id for a in anchors.anchors] == ["author"]
    assert anchors.problems == (AnchorProblem("page_size_mismatch", 3),)


def test__parse__rotated_page__anchors_of_that_page_dropped() -> None:
    raw = _file(_line("sign", "author", "-", 1, 10, 100, 10))

    anchors = parse_positions(raw, [PdfPage(210.0, 297.0, rotate=90)], SHA)

    assert anchors.anchors == ()
    assert anchors.problem_codes() == ("rotated_page",)


@pytest.mark.parametrize(
    "line",
    [
        "sign supervisor - 1 10 10",  # мало полей
        "sign supervisor - 1 10 10 10 10",  # лишнее поле
        "stamp supervisor - 1 10 10 10",  # неизвестный вид
        "sign Supervisor - 1 10 10 10",  # заглавная буква в имени
        "sign 1supervisor - 1 10 10 10",  # имя не с буквы
        "sign " + "a" * 41 + " - 1 10 10 10",  # имя длиннее 40
        "sign supervisor day 1 10 10 10",  # у подписи часть «-»
        "date supervisor - 1 10 10 10",  # у даты часть по грамматике
        "sign supervisor - 0 10 10 10",  # страница с 1
        "sign supervisor - 1 1.5 10 10",  # не целое
        "sign supervisor - 1 10 10 -1",  # отрицательная ширина
        "sign supervisor - 1 10 10 1234567890123",  # длинное число
    ],
)
def test__parse__bad_line__dropped_with_problem(line: str) -> None:
    raw = _file(line, _line("sign", "author", "-", 1, 10, 100, 10))

    anchors = parse_positions(raw, [A4], SHA)

    assert [a.id for a in anchors.anchors] == ["author"]
    assert anchors.problems == (AnchorProblem("bad_line", 2),)


def test__parse__page_beyond_pdf__dropped() -> None:
    raw = _file(_line("sign", "author", "-", 3, 10, 100, 10))

    anchors = parse_positions(raw, [A4, A4], SHA)

    assert anchors.anchors == ()
    assert anchors.problem_codes() == ("page_out_of_range",)


@pytest.mark.parametrize(
    ("x_mm", "from_bottom_mm", "width_mm"),
    [(-1, 100, 10), (205, 100, 10), (10, -1, 10), (10, 298, 10)],
)
def test__parse__outside_page__dropped(x_mm: float, from_bottom_mm: float, width_mm: float) -> None:
    raw = _file(_line("sign", "author", "-", 1, x_mm, from_bottom_mm, width_mm))

    anchors = parse_positions(raw, [A4], SHA)

    assert anchors.anchors == ()
    assert anchors.problem_codes() == ("outside_page",)


def test__parse__line_to_the_right_edge__kept() -> None:
    raw = _file(_line("sign", "author", "-", 1, 200, 0, 10))

    anchors = parse_positions(raw, [A4], SHA)

    assert anchors.anchors == (BuildAnchor("author", AnchorKind.sign, 1, 200.0, 297.0, 10.0),)


def test__parse__repeated_name__first_by_page_then_top_down() -> None:
    raw = _file(
        _line("sign", "supervisor", "-", 2, 10, 280, 10),
        _line("sign", "supervisor", "-", 1, 10, 50, 10),
        _line("sign", "supervisor", "-", 1, 10, 150, 10),
        _line("sign", "author", "-", 1, 10, 60, 10),
    )

    anchors = parse_positions(raw, [A4, A4], SHA)

    assert [(a.id, a.page, a.y_mm) for a in anchors.anchors] == [("supervisor", 1, 147.0), ("author", 1, 237.0)]
    assert anchors.duplicates == ("supervisor",)


def test__parse__no_records__known_and_empty() -> None:
    anchors = parse_positions(_file(), [A4], SHA)

    assert anchors == BuildAnchors(pdf_sha256=SHA)


@pytest.mark.parametrize(
    "header",
    ["", "hsepos 2 39158276 55380990", "hsepos 1 0 55380990", "hsepos 1 a b", "zref 1 1 1", "hsepos 1 1"],
)
def test__parse__unknown_header__whole_file_rejected(header: str) -> None:
    with pytest.raises(PositionsFormatError) as caught:
        parse_positions(_file(_line("sign", "author", "-", 1, 10, 10, 10), header=header), [A4], SHA)

    assert caught.value.code == "unknown_format"


def test__parse__too_large__whole_file_rejected() -> None:
    raw = _file() + b" " * MAX_POSITIONS_BYTES

    with pytest.raises(PositionsFormatError) as caught:
        parse_positions(raw, [A4], SHA)

    assert caught.value.code == "too_large"


def test__parse__over_record_limit__rest_dropped() -> None:
    lines = [_line("sign", f"s{i}", "-", 1, 10, 10, 1) for i in range(MAX_ANCHORS + 5)]

    anchors = parse_positions(_file(*lines), [A4], SHA)

    assert len(anchors.anchors) == MAX_ANCHORS
    assert anchors.problems == (AnchorProblem("too_many_anchors", MAX_ANCHORS + 2),)


def test__parse__not_utf8_line__bad_line() -> None:
    raw = _file() + b"sign \xff - 1 1 1 1\n"

    anchors = parse_positions(raw, [A4], SHA)

    assert anchors.problem_codes() == ("bad_line",)


def test__json__roundtrip() -> None:
    anchors = parse_positions(
        _file(
            _line("sign", "supervisor", "-", 1, 169.5, 110.1, 25.5),
            _line("sign", "supervisor", "-", 1, 169.5, 10, 25.5),
            "garbage",
        ),
        [A4],
        SHA,
    )

    assert decode_anchors(encode_anchors(anchors)) == anchors
    body = json.loads(encode_anchors(anchors))
    assert body["format"] == 1
    assert body["pdf_sha256"] == SHA
    assert body["anchors"] == [
        {"id": "supervisor", "kind": "sign", "page": 1, "x_mm": 169.5, "y_mm": 186.9, "width_mm": 25.5}
    ]
    assert body["duplicates"] == ["supervisor"]
    assert body["problems"] == [{"code": "bad_line", "line": 4}]


def _doc(**override: object) -> bytes:
    body: dict[str, object] = {
        "format": 1,
        "pdf_sha256": SHA,
        "anchors": [{"id": "supervisor.day", "kind": "date", "page": 1, "x_mm": 1, "y_mm": 2.5, "width_mm": 0}],
        "duplicates": [],
        "problems": [],
    }
    body.update(override)
    return json.dumps(body).encode()


def test__decode__valid__parsed() -> None:
    decoded = decode_anchors(_doc())

    assert decoded is not None
    assert decoded.anchors == (BuildAnchor("supervisor.day", AnchorKind.date, 1, 1.0, 2.5, 0.0),)


@pytest.mark.parametrize(
    "raw",
    [
        b"not json",
        b"[]",
        _doc(format=2),
        _doc(pdf_sha256="short"),
        _doc(anchors="x"),
        _doc(anchors=[{"id": "supervisor", "kind": "date", "page": 1, "x_mm": 1, "y_mm": 1, "width_mm": 1}]),
        _doc(anchors=[{"id": "supervisor.day", "kind": "sign", "page": 1, "x_mm": 1, "y_mm": 1, "width_mm": 1}]),
        _doc(anchors=[{"id": "../x", "kind": "sign", "page": 1, "x_mm": 1, "y_mm": 1, "width_mm": 1}]),
        _doc(anchors=[{"id": "a", "kind": "sign", "page": 0, "x_mm": 1, "y_mm": 1, "width_mm": 1}]),
        _doc(anchors=[{"id": "a", "kind": "sign", "page": True, "x_mm": 1, "y_mm": 1, "width_mm": 1}]),
        _doc(anchors=[{"id": "a", "kind": "sign", "page": 1, "x_mm": "1", "y_mm": 1, "width_mm": 1}]),
        _doc(anchors=[{"id": "a", "kind": "sign", "page": 1, "x_mm": 1e9, "y_mm": 1, "width_mm": 1}]),
        _doc(anchors=[{"id": "a", "kind": "sign", "page": 1, "x_mm": 1, "y_mm": 1, "width_mm": -1}]),
        _doc(anchors=[{"id": "a", "kind": "sign", "page": 1, "x_mm": 1, "y_mm": 1}]),
        _doc(anchors=[{"id": "a", "kind": "sign", "page": 1, "x_mm": 1, "y_mm": 1, "width_mm": 1}] * 2),
        _doc(duplicates=["Bad"]),
        _doc(problems=[{"code": "whatever", "line": 1}]),
        _doc(problems=[{"code": "bad_line", "line": 0}]),
        b"[" * 100 + b"]" * 100,
    ],
)
def test__decode__wrong_shape__unknown(raw: bytes) -> None:
    assert decode_anchors(raw) is None


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [
        ("supervisor", None, True),
        ("supervisor", AnchorKind.sign, True),
        ("supervisor", AnchorKind.date, False),
        ("supervisor.month_word", AnchorKind.date, True),
        ("supervisor.month_word", AnchorKind.sign, False),
        ("supervisor.", None, False),
        ("a.b.c", None, False),
        ("", None, False),
    ],
)
def test__is_anchor_id(value: str, kind: AnchorKind | None, expected: bool) -> None:
    assert is_anchor_id(value, kind) is expected
