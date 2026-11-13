"""Якоря сборки: где в собранном PDF стоят строки подписей и дат шаблона (docs/design/signing-route.md, 15.17).

Макросы шаблона (`\\hseSignAnchor`, `\\hseDateAnchor`, файл пака `common/anchors.tex`) пишут при сборке файл позиций
`<jobname>.hsepos` в каталог сборки. Студия переводит его при публикации PDF в `<stem>.anchors.json` рядом с ним и
привязывает к sha256 этого PDF: якоря известны, только пока источник подписи документа тот же PDF.

Файл позиций пишет код пользователя, а копия якорей версии на подписи приходит через git, поэтому оба разбираются
строго и с пределами. Здесь только формы и разбор, без файловой системы.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

from hse_doc_studio.core.git_sync.untrusted_json import loads_untrusted

ANCHORS_FORMAT: Final = 1
POSITIONS_SUFFIX: Final = ".hsepos"
ANCHORS_SUFFIX: Final = ".anchors.json"

# Пределы файла позиций (15.17.4): больше в шаблоне не бывает, остальное мусор или попытка забить диск.
MAX_POSITIONS_BYTES: Final = 64 * 1024
MAX_ANCHORS: Final = 256
# Проблем в `anchors.json` не больше этого: это подсказка автору пака, а не журнал.
MAX_PROBLEMS: Final = 64
MAX_ANCHORS_JSON_BYTES: Final = 256 * 1024

# Расхождение размера страницы PDF с `\paperwidth`/`\paperheight` больше этого: шаблон задал бумагу мимо `geometry`.
PAGE_SIZE_TOLERANCE_MM: Final = 1.0
# Запас на округление на краю листа: линия до самого края листа остаётся внутри.
_EDGE_MM: Final = 0.01

_SP_PER_PT: Final = 65536
_PT_PER_IN: Final = 72.27
_MM_PER_IN: Final = 25.4
_BP_PER_IN: Final = 72.0

# Имя якоря и часть даты (15.17.3): id слота каталога или формат метки даты.
NAME_RE: Final = re.compile(r"[a-z][a-z0-9_]{0,39}")
_INT_RE: Final = re.compile(r"-?\d{1,12}")
_SHA256_RE: Final = re.compile(r"[0-9a-f]{64}")
_SIGN_PART: Final = "-"
_HEADER: Final = "hsepos"
_FIELDS: Final = 7
_MAX_MM: Final = 10000.0

# Коды проблем разбора.
PROBLEM_BAD_LINE: Final = "bad_line"
PROBLEM_PAGE_OUT_OF_RANGE: Final = "page_out_of_range"
PROBLEM_OUTSIDE_PAGE: Final = "outside_page"
PROBLEM_PAGE_SIZE_MISMATCH: Final = "page_size_mismatch"
PROBLEM_ROTATED_PAGE: Final = "rotated_page"
PROBLEM_TOO_MANY_ANCHORS: Final = "too_many_anchors"
PROBLEM_CODES: Final = frozenset(
    {
        PROBLEM_BAD_LINE,
        PROBLEM_PAGE_OUT_OF_RANGE,
        PROBLEM_OUTSIDE_PAGE,
        PROBLEM_PAGE_SIZE_MISMATCH,
        PROBLEM_ROTATED_PAGE,
        PROBLEM_TOO_MANY_ANCHORS,
    }
)

# Файл позиций непригоден целиком: якоря неизвестны, `anchors.json` не пишется.
FORMAT_UNKNOWN: Final = "unknown_format"
FORMAT_TOO_LARGE: Final = "too_large"


class AnchorKind(StrEnum):
    sign = "sign"
    date = "date"


@dataclass(frozen=True)
class BuildAnchor:
    """Якорь в мм от левого верхнего угла страницы: `x_mm` левый конец линии, `y_mm` её базовая линия."""

    id: str
    kind: AnchorKind
    page: int
    x_mm: float
    y_mm: float
    width_mm: float


@dataclass(frozen=True)
class AnchorProblem:
    """Отброшенная строка файла позиций: код и номер строки (с 1, заголовок это строка 1)."""

    code: str
    line: int


@dataclass(frozen=True)
class BuildAnchors:
    """Якоря одной сборки (`anchors.json`). Пустой `anchors` при известных якорях значит, что строк в документе нет."""

    pdf_sha256: str
    anchors: tuple[BuildAnchor, ...] = ()
    duplicates: tuple[str, ...] = ()
    problems: tuple[AnchorProblem, ...] = ()
    format: int = ANCHORS_FORMAT

    @property
    def build(self) -> str:
        """Короткий отпечаток сборки (первые 16 знаков sha256 PDF): так его пишет пометка места (15.17.10)."""
        return self.pdf_sha256[:16]

    def of(self, pdf_sha256: str | None) -> bool:
        """Якоря от этого PDF: иначе для него они неизвестны."""
        return pdf_sha256 is not None and pdf_sha256 == self.pdf_sha256

    def get(self, anchor_id: str) -> BuildAnchor | None:
        return next((anchor for anchor in self.anchors if anchor.id == anchor_id), None)

    def problem_codes(self) -> tuple[str, ...]:
        """Коды проблем без повторов в порядке первого появления."""
        return tuple(dict.fromkeys(problem.code for problem in self.problems))


@dataclass(frozen=True)
class PdfPage:
    """Страница PDF: размер `MediaBox` в мм и поворот `/Rotate` в градусах."""

    width_mm: float
    height_mm: float
    rotate: int = 0


class PositionsFormatError(ValueError):
    """Файл позиций непригоден целиком (`unknown_format`, `too_large`): якоря сборки неизвестны."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def anchor_id(kind: AnchorKind, name: str, part: str) -> str:
    """id якоря: имя у подписи, «имя.часть» у даты (`supervisor.day`)."""
    return name if kind is AnchorKind.sign else f"{name}.{part}"


def is_anchor_id(value: str, kind: AnchorKind | None = None) -> bool:
    name, dot, part = value.partition(".")
    if not NAME_RE.fullmatch(name):
        return False
    if not dot:
        return kind in (None, AnchorKind.sign)
    return kind in (None, AnchorKind.date) and NAME_RE.fullmatch(part) is not None


def sp_to_mm(sp: int) -> float:
    return sp / _SP_PER_PT / _PT_PER_IN * _MM_PER_IN


def bp_to_mm(bp: float) -> float:
    return bp / _BP_PER_IN * _MM_PER_IN


# --- файл позиций ---


@dataclass(frozen=True)
class _Paper:
    width_mm: float
    height_mm: float


@dataclass(frozen=True)
class _Raw:
    kind: AnchorKind
    name: str
    part: str
    page: int
    x: int
    y: int
    width: int


def parse_positions(raw: bytes, pages: Sequence[PdfPage], pdf_sha256: str) -> BuildAnchors:
    """Разбор `<jobname>.hsepos` в якоря PDF с этими страницами (15.17.4).

    Битая строка отбрасывается с проблемой, файл с неизвестным заголовком или больше предела целиком
    (`PositionsFormatError`). Высота страницы берётся из PDF, а не из `\\paperheight`: при расхождении больше 1 мм
    и у повёрнутой страницы якоря этой страницы отбрасываются. Повтор имени: берётся первый по странице и сверху
    вниз, имя попадает в `duplicates`.
    """
    if len(raw) > MAX_POSITIONS_BYTES:
        raise PositionsFormatError(FORMAT_TOO_LARGE)
    lines = raw.split(b"\n")
    paper = _header(lines[0])
    problems: list[AnchorProblem] = []
    found: dict[str, list[BuildAnchor]] = {}
    records = 0
    for number, line in enumerate(lines[1:], start=2):
        text = line.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        records += 1
        if records > MAX_ANCHORS:
            _note(problems, PROBLEM_TOO_MANY_ANCHORS, number)
            break
        record = _record(text)
        if record is None:
            _note(problems, PROBLEM_BAD_LINE, number)
            continue
        anchor = _placed(record, paper, pages)
        if isinstance(anchor, str):
            _note(problems, anchor, number)
            continue
        found.setdefault(anchor.id, []).append(anchor)
    anchors = sorted((min(same, key=_reading_order) for same in found.values()), key=_reading_order)
    return BuildAnchors(
        pdf_sha256=pdf_sha256,
        anchors=tuple(anchors),
        duplicates=tuple(sorted(name for name, same in found.items() if len(same) > 1)),
        problems=tuple(problems),
    )


def _note(problems: list[AnchorProblem], code: str, line: int) -> None:
    if len(problems) < MAX_PROBLEMS:
        problems.append(AnchorProblem(code, line))


def _reading_order(anchor: BuildAnchor) -> tuple[int, float, float, str]:
    return (anchor.page, anchor.y_mm, anchor.x_mm, anchor.id)


def _header(line: bytes) -> _Paper:
    try:
        parts = line.decode("ascii").strip().split()
    except UnicodeDecodeError:
        raise PositionsFormatError(FORMAT_UNKNOWN) from None
    if len(parts) != 4 or parts[0] != _HEADER or parts[1] != str(ANCHORS_FORMAT):
        raise PositionsFormatError(FORMAT_UNKNOWN)
    if not all(_INT_RE.fullmatch(value) for value in parts[2:]):
        raise PositionsFormatError(FORMAT_UNKNOWN)
    width, height = int(parts[2]), int(parts[3])
    if width <= 0 or height <= 0:
        raise PositionsFormatError(FORMAT_UNKNOWN)
    return _Paper(sp_to_mm(width), sp_to_mm(height))


def _record(text: str) -> _Raw | None:
    parts = text.split()
    if len(parts) != _FIELDS:
        return None
    kind_text, name, part, *numbers = parts
    if kind_text not in AnchorKind.__members__ or not NAME_RE.fullmatch(name):
        return None
    kind = AnchorKind(kind_text)
    if (kind is AnchorKind.sign and part != _SIGN_PART) or (kind is AnchorKind.date and not NAME_RE.fullmatch(part)):
        return None
    if not all(_INT_RE.fullmatch(value) for value in numbers):
        return None
    page, x, y, width = (int(value) for value in numbers)
    if page < 1 or width < 0:
        return None
    return _Raw(kind, name, part, page, x, y, width)


def _placed(record: _Raw, paper: _Paper, pages: Sequence[PdfPage]) -> BuildAnchor | str:
    """Якорь в мм страницы PDF или код проблемы, по которой строка отброшена."""
    if record.page > len(pages):
        return PROBLEM_PAGE_OUT_OF_RANGE
    page = pages[record.page - 1]
    if page.rotate % 360 != 0:
        return PROBLEM_ROTATED_PAGE
    if (
        abs(page.width_mm - paper.width_mm) > PAGE_SIZE_TOLERANCE_MM
        or abs(page.height_mm - paper.height_mm) > PAGE_SIZE_TOLERANCE_MM
    ):
        return PROBLEM_PAGE_SIZE_MISMATCH
    x_mm = sp_to_mm(record.x)
    from_bottom = sp_to_mm(record.y)
    width_mm = sp_to_mm(record.width)
    if (
        x_mm < -_EDGE_MM
        or x_mm + width_mm > page.width_mm + _EDGE_MM
        or from_bottom < -_EDGE_MM
        or from_bottom > page.height_mm + _EDGE_MM
    ):
        return PROBLEM_OUTSIDE_PAGE
    return BuildAnchor(
        id=anchor_id(record.kind, record.name, record.part),
        kind=record.kind,
        page=record.page,
        x_mm=_mm(x_mm),
        y_mm=_mm(page.height_mm - from_bottom),
        width_mm=_mm(width_mm),
    )


def _mm(value: float) -> float:
    """Округление до 0,1 мм, как у мест; без «-0.0» у точки на краю листа."""
    return round(value, 1) + 0.0


# --- anchors.json ---


def encode_anchors(anchors: BuildAnchors) -> bytes:
    payload = {
        "format": anchors.format,
        "pdf_sha256": anchors.pdf_sha256,
        "anchors": [
            {
                "id": a.id,
                "kind": a.kind.value,
                "page": a.page,
                "x_mm": a.x_mm,
                "y_mm": a.y_mm,
                "width_mm": a.width_mm,
            }
            for a in anchors.anchors
        ],
        "duplicates": list(anchors.duplicates),
        "problems": [{"code": p.code, "line": p.line} for p in anchors.problems],
    }
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def decode_anchors(raw: bytes) -> BuildAnchors | None:
    """`anchors.json` или None, если файл не той формы: тогда якоря неизвестны.

    Копия версии на подписи приходит через git, поэтому разбор строгий: неизвестный формат, лишние или битые поля,
    повтор id и выход за пределы дают None, а не частичный результат.
    """
    if len(raw) > MAX_ANCHORS_JSON_BYTES:
        return None
    try:
        data: Any = loads_untrusted(raw)
        return _decoded(data)
    except (ValueError, TypeError, KeyError):
        return None


def _decoded(data: Any) -> BuildAnchors:
    """Разобранный документ; любое расхождение с формой бросает ValueError, TypeError или KeyError."""
    if not isinstance(data, dict) or data.get("format") != ANCHORS_FORMAT:
        raise ValueError("unknown anchors format")
    sha = data["pdf_sha256"]
    items, duplicates, problems = data["anchors"], data.get("duplicates", []), data.get("problems", [])
    if not isinstance(sha, str) or not _SHA256_RE.fullmatch(sha):
        raise ValueError("bad pdf_sha256")
    if not isinstance(items, list) or not isinstance(duplicates, list) or not isinstance(problems, list):
        raise TypeError("anchors, duplicates and problems are lists")
    if len(items) > MAX_ANCHORS or len(duplicates) > MAX_ANCHORS or len(problems) > MAX_PROBLEMS:
        raise ValueError("too many entries")
    anchors = tuple(_anchor(item) for item in items)
    if len({a.id for a in anchors}) != len(anchors):
        raise ValueError("repeated anchor id")
    if not all(isinstance(name, str) and is_anchor_id(name) for name in duplicates):
        raise ValueError("bad duplicate id")
    return BuildAnchors(
        pdf_sha256=sha,
        anchors=anchors,
        duplicates=tuple(duplicates),
        problems=tuple(_problem(item) for item in problems),
    )


def _anchor(item: Any) -> BuildAnchor:
    if not isinstance(item, dict):
        raise TypeError("anchor is not an object")
    kind = AnchorKind(item["kind"])
    ident, page = item["id"], item["page"]
    if not isinstance(ident, str) or not is_anchor_id(ident, kind):
        raise ValueError("bad anchor id")
    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ValueError("bad page")
    x_mm, y_mm, width_mm = (_number(item[key]) for key in ("x_mm", "y_mm", "width_mm"))
    if width_mm < 0:
        raise ValueError("bad width")
    return BuildAnchor(id=ident, kind=kind, page=page, x_mm=x_mm, y_mm=y_mm, width_mm=width_mm)


def _problem(item: Any) -> AnchorProblem:
    if not isinstance(item, dict):
        raise TypeError("problem is not an object")
    code, line = item["code"], item["line"]
    if not isinstance(code, str) or code not in PROBLEM_CODES:
        raise ValueError("bad problem code")
    if isinstance(line, bool) or not isinstance(line, int) or line < 1:
        raise ValueError("bad problem line")
    return AnchorProblem(code, line)


def _number(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("not a number")
    number = float(value)
    if not math.isfinite(number) or abs(number) > _MAX_MM:
        raise ValueError("number out of range")
    return number
