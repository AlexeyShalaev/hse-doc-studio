"""Проверка мест подписей на PDF предпросмотра (pack-studio-mcp.md, 4.4): чистая модель страницы и правила.

Агент ставит места подписей сам: смотрит на картинку страницы и просит эту проверку подтвердить, что каждая рамка
стоит где нужно. На вход страница PDF, как её видит адаптер (`IPdfPages`): размер, знаки текстового слоя с рамками,
отрезки рисунка, рамки картинок; рамки мест сборки (как их посчитала модель мест, `DocFrame.box`), якоря сборки и доля
«чернил» под каждой рамкой. На выходе находки по слоту и предложенная рамка.

Координаты везде в мм от левого верхнего угла страницы, ось y вниз, как у мест в `version.yaml`.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Final

from hse_doc_studio.core.catalog import ANCHOR_DEFAULT_DY_MM

# Высота рамки картинки подписи: ширина на пропорцию картинки, по умолчанию 0,4 (`core/signatures/stamps.py`).
SIGN_ASPECT: Final = 0.4
# Поле печати: ближе к краю листа рамка рискует обрезаться принтером.
PRINT_MARGIN_MM: Final = 5.0
# Линия подписи: горизонтальный отрезок не короче 15 мм и не толще 1,2 мм; шире 70 % листа это линейка оформления.
LINE_MIN_MM: Final = 15.0
LINE_MAX_THICK_MM: Final = 1.2
LINE_MAX_SHARE: Final = 0.7
# Ряд подчёркиваний «____» не короче четырёх знаков тоже линия подписи.
UNDERSCORES_MIN: Final = 4
# Знак закрыт рамкой, если она накрывает не меньше этой доли его площади.
CHAR_COVER: Final = 0.4
# Доля не белых пикселей под рамкой без линий и подписей к ним, выше которой под подписью что-то нарисовано.
BUSY_INK: Final = 0.06
# Линия «под рамкой»: проходит через нижние 65 % рамки или не ниже 2 мм под ней, по горизонтали перекрытие от половины.
_ON_LINE_TOP: Final = 0.35
_ON_LINE_BELOW_MM: Final = 2.0
_ON_LINE_OVERLAP: Final = 0.5
# Подпись слота рядом с линией: на той же строке (до 6 мм по вертикали) или выше до 14 мм.
_ROW_MM: Final = 6.0
_ABOVE_MM: Final = 14.0
# Заголовок колонки («Научный руководитель» над столбцом строк титула) не выше этого над линией.
_COLUMN_MM: Final = 60.0
# Якорь уже этого это точка отсчёта, а не строка подписи: место на нём не сверяется с линией.
_POINT_ANCHOR_MM: Final = 5.0
# Мелкий текст (подпись под строкой «И.О. Фамилия»): закрыть его хуже не ошибка, а замечание.
_SMALL_TEXT_MM: Final = 2.6
# Дальше этого линия не считается «рядом» с рамкой, если её не назвали подписью слота.
_NEAR_MM: Final = 60.0
_MIN_WIDTH_MM: Final = 20.0

# Слова у строки подписи, которые рамка может накрывать: подпись под линией, место печати.
_CAPTIONS: Final = re.compile(
    r"^\(?(подпись|signature|подп\.?|м\.?\s?п\.?|дата|date|расшифровка подписи)\)?[.,:;]?$", re.I
)
_WORD: Final = re.compile(r"[a-zа-яё]{4,}", re.I)


class Severity(StrEnum):
    error = "error"
    warning = "warning"
    info = "info"


class Code(StrEnum):
    no_place = "no_place"
    page_out_of_range = "page_out_of_range"
    outside_page = "outside_page"
    near_edge = "near_edge"
    overlaps_text = "overlaps_text"
    overlaps_place = "overlaps_place"
    busy_area = "busy_area"
    far_from_line = "far_from_line"
    no_line = "no_line"
    anchor_available = "anchor_available"


SEVERITY: Final[Mapping[Code, Severity]] = {
    Code.no_place: Severity.error,
    Code.page_out_of_range: Severity.error,
    Code.outside_page: Severity.error,
    Code.near_edge: Severity.warning,
    Code.overlaps_text: Severity.error,
    Code.overlaps_place: Severity.error,
    Code.busy_area: Severity.warning,
    Code.far_from_line: Severity.warning,
    Code.no_line: Severity.info,
    Code.anchor_available: Severity.info,
}


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def overlap(self, other: Rect) -> float:
        w = min(self.x1, other.x1) - max(self.x0, other.x0)
        h = min(self.y1, other.y1) - max(self.y0, other.y0)
        return w * h if w > 0 and h > 0 else 0.0

    def h_overlap(self, other: Rect) -> float:
        return max(0.0, min(self.x1, other.x1) - max(self.x0, other.x0))

    def rounded(self) -> Rect:
        return Rect(round(self.x0, 1), round(self.y0, 1), round(self.x1, 1), round(self.y1, 1))


def sign_rect(x_mm: float, y_mm: float, width_mm: float) -> Rect:
    """Рамка картинки подписи: верх `y_mm`, высота ширина на `SIGN_ASPECT`."""
    return Rect(x_mm, y_mm, x_mm + width_mm, y_mm + width_mm * SIGN_ASPECT)


@dataclass(frozen=True)
class Glyph:
    text: str
    rect: Rect


@dataclass(frozen=True)
class Word:
    text: str
    rect: Rect


class LineSource(StrEnum):
    anchor = "anchor"
    drawing = "drawing"
    underscores = "underscores"


@dataclass(frozen=True)
class Line:
    """Строка подписи: отрезок на высоте `y` от `x0` до `x1`."""

    x0: float
    x1: float
    y: float
    source: LineSource
    anchor: str | None = None

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    def rect(self) -> Rect:
        return Rect(self.x0, self.y - 0.3, self.x1, self.y + 0.3)


@dataclass(frozen=True)
class PageLayout:
    """Страница PDF: размер, знаки, слова, отрезки-линии и рамки картинок (всё в мм от левого верхнего угла)."""

    page: int
    width_mm: float
    height_mm: float
    glyphs: tuple[Glyph, ...] = ()
    words: tuple[Word, ...] = ()
    lines: tuple[Line, ...] = ()
    images: tuple[Rect, ...] = ()


class PlaceKind(StrEnum):
    sign = "sign"
    date = "date"


@dataclass(frozen=True)
class Place:
    """Рамка места сборки: слот, его подпись для людей, страница, рамка, откуда место и якорь записи."""

    slot: str
    label: str
    page: int
    rect: Rect
    kind: PlaceKind = PlaceKind.sign
    origin: str = "mm"  # mm | anchor | fallback
    anchor: str | None = None
    words: tuple[str, ...] = ()  # слова подписи слота на всех языках пака


@dataclass(frozen=True)
class Finding:
    code: Code
    severity: Severity
    data: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SlotCheck:
    slot: str
    label: str
    page: int | None
    rect: Rect | None
    findings: tuple[Finding, ...]
    line: Line | None = None
    line_page: int | None = None
    suggested: Rect | None = None
    bind_anchor: bool = False

    @property
    def status(self) -> Severity | None:
        levels = {f.severity for f in self.findings}
        for level in (Severity.error, Severity.warning):
            if level in levels:
                return level
        return None


def is_caption(text: str) -> bool:
    return bool(_CAPTIONS.match(text.strip()))


def label_words(*labels: str) -> tuple[str, ...]:
    """Основы слов подписи слота (первые пять букв слов от четырёх букв) для поиска строки слота в тексте."""
    stems: dict[str, None] = {}
    for label in labels:
        for match in _WORD.finditer(label):
            stems[match.group(0).casefold()[:5]] = None
    return tuple(stems)


def words_of(glyphs: Sequence[Glyph]) -> tuple[Word, ...]:
    """Слова из знаков по порядку текстового слоя: разрыв по пробелу, переводу строки и скачку по горизонтали."""
    words: list[Word] = []
    text = ""
    rect: Rect | None = None
    last: Rect | None = None
    for glyph in glyphs:
        gap = last is not None and (
            glyph.rect.x0 - last.x1 > max(1.5, last.height * 0.6) or abs(glyph.rect.cy - last.cy) > 2.5
        )
        if glyph.text.isspace() or not glyph.text or gap:
            if text and rect is not None:
                words.append(Word(text, rect))
            text, rect = "", None
            if glyph.text.isspace() or not glyph.text:
                last = None
                continue
        text += glyph.text
        rect = (
            glyph.rect
            if rect is None
            else Rect(
                min(rect.x0, glyph.rect.x0),
                min(rect.y0, glyph.rect.y0),
                max(rect.x1, glyph.rect.x1),
                max(rect.y1, glyph.rect.y1),
            )
        )
        last = glyph.rect
    if text and rect is not None:
        words.append(Word(text, rect))
    return tuple(words)


def underscore_lines(words: Sequence[Word]) -> tuple[Line, ...]:
    """Ряды подчёркиваний «____» как строки подписи: низ ряда это линия."""
    found: list[Line] = []
    for word in words:
        for match in re.finditer(r"_{%d,}" % UNDERSCORES_MIN, word.text):  # noqa: UP031 — квантификатор регулярки
            share = word.rect.width / max(len(word.text), 1)
            x0 = word.rect.x0 + match.start() * share
            x1 = word.rect.x0 + match.end() * share
            found.append(Line(x0, x1, word.rect.y1, LineSource.underscores))
    return tuple(found)


def is_sign_line(rect: Rect, page_width: float) -> bool:
    return LINE_MIN_MM <= rect.width <= page_width * LINE_MAX_SHARE and rect.height <= LINE_MAX_THICK_MM


def on_line(rect: Rect, line: Line) -> bool:
    """Рамка стоит на линии: линия в нижней части рамки (или чуть ниже) и перекрытие по горизонтали от половины."""
    top = rect.y0 + rect.height * _ON_LINE_TOP
    if not top <= line.y <= rect.y1 + _ON_LINE_BELOW_MM:
        return False
    return rect.h_overlap(line.rect()) >= _ON_LINE_OVERLAP * min(rect.width, line.width)


def _distance(rect: Rect, line: Line) -> float:
    dx = max(0.0, line.x0 - rect.x1, rect.x0 - line.x1)
    dy = line.y - rect.y1 if line.y > rect.y1 else rect.y0 - line.y if line.y < rect.y0 else 0.0
    return (dx * dx + dy * dy) ** 0.5


def _score(line: Line, words: Sequence[Word], stems: Sequence[str]) -> int:
    """Насколько линия «своя» для слота: по два очка за каждую основу подписи слота рядом (на той же строке левее,
    выше до 14 мм или в заголовке колонки над линией до 60 мм) и очко за подпись «(подпись)» под линией."""
    found: set[str] = set()
    caption = 0
    column = Rect(line.x0 - 10, 0, line.x1 + 10, 1)
    for word in words:
        dy = line.y - word.rect.y1
        if is_caption(word.text) and -_ROW_MM <= dy < 0 and word.rect.h_overlap(column) > 0:
            caption = 1
        same_row = abs(dy) <= _ROW_MM and word.rect.x1 <= line.x1
        above = 0 < dy <= _ABOVE_MM and word.rect.h_overlap(Rect(line.x0 - 60, 0, line.x1, 1)) > 0
        heading = 0 < dy <= _COLUMN_MM and column.x0 <= word.rect.x0 <= column.x1
        if same_row or above or heading:
            text = word.text.casefold()
            found.update(stem for stem in stems if text.startswith(stem))
    return 2 * len(found) + caption


def _covered_text(rect: Rect, glyphs: Sequence[Glyph], words: Sequence[Word]) -> str:
    """Закрытый рамкой текст с пробелами, как в тексте страницы; подписи у линии и подчёркивания не в счёт."""
    captions = [w.rect for w in words if is_caption(w.text)]
    out: list[str] = []
    for glyph in glyphs:
        visible = not glyph.text.isspace() and glyph.text != "_" and glyph.rect.area > 0
        covered = (
            visible
            and rect.overlap(glyph.rect) >= CHAR_COVER * glyph.rect.area
            and not any(c.overlap(glyph.rect) >= 0.5 * glyph.rect.area for c in captions)
        )
        if covered:
            out.append(glyph.text)
        elif out and out[-1] != " ":
            out.append(" ")
    return "".join(out).strip()


def suggest(line: Line, width: float, layout: PageLayout, others: Sequence[Rect]) -> Rect | None:
    """Рамка над линией: ширина прежняя (не шире линии плюс 10 мм), центр над серединой линии, верх на 10 мм выше
    линии, как у места на якоре по умолчанию; если так она закрывает текст или чужую рамку, низ на 1 мм ниже линии.
    Плохая рамка не предлагается."""
    w = max(min(width, line.width + 10.0), min(_MIN_WIDTH_MM, line.width + 10.0))
    x0 = min(max(line.cx - w / 2, PRINT_MARGIN_MM), layout.width_mm - PRINT_MARGIN_MM - w)
    for top in (line.y + ANCHOR_DEFAULT_DY_MM, line.y + 1.0 - w * SIGN_ASPECT):
        candidate = sign_rect(round(x0), round(top), round(w))
        if candidate.y0 < PRINT_MARGIN_MM or candidate.y1 > layout.height_mm - PRINT_MARGIN_MM:
            continue
        if not on_line(candidate, line):
            continue
        if _covered_text(candidate, layout.glyphs, layout.words):
            continue
        if any(candidate.overlap(o) > 0 for o in others):
            continue
        return candidate
    return None


@dataclass(frozen=True)
class _Claim:
    slot: str
    line: Line


def _pick_line(place: Place, layout: PageLayout, claimed: Sequence[_Claim]) -> Line | None:
    """Своя линия слота на странице рамки: больше всего очков `_score`, при равенстве ближе к рамке; без очков
    ближайшая свободная не дальше 60 мм."""
    lines = [ln for ln in layout.lines if ln.source is not LineSource.anchor]
    taken = {(c.line.x0, c.line.y) for c in claimed if c.slot != place.slot}
    free = [ln for ln in lines if (ln.x0, ln.y) not in taken]
    scored = [(_score(ln, layout.words, place.words), ln) for ln in free]
    best = max((score for score, _ in scored), default=0)
    pool = (
        [ln for score, ln in scored if score == best]
        if best >= 2  # noqa: PLR2004 — хотя бы одна основа подписи слота
        else [ln for ln in free if _distance(place.rect, ln) <= _NEAR_MM]
    )
    if not pool:
        return None
    return min(pool, key=lambda ln: _distance(place.rect, ln))


def check_places(  # noqa: C901, PLR0912, PLR0915 — правила раздела 4.4 по очереди
    places: Sequence[Place],
    missing: Sequence[tuple[str, str]],
    layouts: Mapping[int, PageLayout],
    page_count: int,
    ink: Mapping[int, float],
    anchors: Mapping[str, tuple[int, Line]] | None = None,
) -> tuple[SlotCheck, ...]:
    """Находки по местам подписей сборки.

    `places` рамки сборки (подписи и метки даты), `missing` слоты документа без рамки (id и подпись), `layouts`
    страницы с рамками и якорями, `ink` доля чернил под рамкой подписи по индексу в `places`, `anchors` линии якорей
    подписей сборки по id слота (страница и линия).
    """
    anchors = anchors or {}
    result: list[SlotCheck] = [
        SlotCheck(slot, label, None, None, (Finding(Code.no_place, SEVERITY[Code.no_place]),))
        for slot, label in missing
    ]
    signs = [(i, p) for i, p in enumerate(places) if p.kind is PlaceKind.sign]
    claims: list[_Claim] = []
    for _, place in signs:
        layout = layouts.get(place.page)
        if layout is None:
            continue
        line = next((ln for ln in layout.lines if on_line(place.rect, ln)), None)
        if line is not None:
            claims.append(_Claim(place.slot, line))
    for index, place in signs:
        findings: list[Finding] = []

        def add(code: Code, **data: object) -> None:
            findings.append(Finding(code, SEVERITY[code], data))  # noqa: B023 — список этого слота

        layout = layouts.get(place.page)
        if place.page > page_count or layout is None:
            add(Code.page_out_of_range, page=place.page, pages=page_count)
            result.append(SlotCheck(place.slot, place.label, place.page, place.rect, tuple(findings)))
            continue
        rect = place.rect
        if rect.x0 < 0 or rect.y0 < 0 or rect.x1 > layout.width_mm + 0.01 or rect.y1 > layout.height_mm + 0.01:
            add(Code.outside_page, width_mm=layout.width_mm, height_mm=layout.height_mm)
        elif min(rect.x0, rect.y0, layout.width_mm - rect.x1, layout.height_mm - rect.y1) < PRINT_MARGIN_MM:
            add(Code.near_edge, margin_mm=PRINT_MARGIN_MM)
        hidden = _covered_text(rect, layout.glyphs, layout.words)
        if hidden:
            small = _all_small(rect, layout.glyphs)
            findings.append(
                Finding(
                    Code.overlaps_text,
                    Severity.warning if small else Severity.error,
                    {"text": hidden[:60], "small": small},
                )
            )
        others = [p for p in places if p is not place and p.page == place.page and p.slot != place.slot]
        hit = [p for p in others if rect.overlap(p.rect) > 0]
        if hit:
            add(Code.overlaps_place, slots=sorted({p.slot for p in hit}), kinds=sorted({p.kind.value for p in hit}))
        share = ink.get(index)
        if share is not None and share > BUSY_INK and not hidden:
            add(Code.busy_area, ink=round(share, 3))
        own = anchors.get(place.slot)
        line_page, line = own if own is not None else (place.page, _pick_line(place, layout, claims))
        anchor_line = own is not None
        point = own is not None and own[1].width < _POINT_ANCHOR_MM
        if point and place.origin == "anchor":
            # Якорь-точка: рамку ставит смещение записи, где задумал автор пака; линией её не проверить.
            line = None
        elif line is None:
            add(Code.no_line)
        elif line_page != place.page:
            add(Code.far_from_line, line=_line_data(line), line_page=line_page)
        elif not on_line(rect, line):
            add(Code.far_from_line, line=_line_data(line), distance_mm=round(_distance(rect, line), 1))
        if anchor_line and place.origin != "anchor":
            add(Code.anchor_available, anchor=place.slot)
        suggested = None
        bad = any(f.severity is not Severity.info for f in findings)
        line_layout = layouts.get(line_page)
        if line is not None and bad and line_layout is not None:
            blockers = [p.rect for p in places if p.page == line_page and p.slot != place.slot]
            suggested = suggest(line, rect.width, line_layout, blockers)
        result.append(
            SlotCheck(
                place.slot,
                place.label,
                place.page,
                rect,
                tuple(findings),
                line=line,
                line_page=line_page if line is not None else None,
                suggested=suggested,
                bind_anchor=anchor_line and place.origin != "anchor",
            )
        )
    for place in places:
        if place.kind is not PlaceKind.date:
            continue
        layout = layouts.get(place.page)
        findings = []
        if place.page > page_count or layout is None:
            findings.append(Finding(Code.page_out_of_range, Severity.error, {"page": place.page, "pages": page_count}))
        else:
            r = place.rect
            if r.x0 < 0 or r.y0 < 0 or r.x1 > layout.width_mm + 0.01 or r.y1 > layout.height_mm + 0.01:
                findings.append(Finding(Code.outside_page, Severity.error, {}))
            hit = [p for p in places if p.page == place.page and p.slot != place.slot and r.overlap(p.rect) > 0]
            if hit:
                findings.append(
                    Finding(Code.overlaps_place, Severity.error, {"slots": sorted({p.slot for p in hit}), "date": True})
                )
        if findings:
            result.append(SlotCheck(f"{place.slot}.date", place.label, place.page, place.rect, tuple(findings)))
    return tuple(result)


def _all_small(rect: Rect, glyphs: Sequence[Glyph]) -> bool:
    covered = [g for g in glyphs if not g.text.isspace() and g.text != "_" and rect.overlap(g.rect) > 0]
    return bool(covered) and all(g.rect.height < _SMALL_TEXT_MM for g in covered)


def _line_data(line: Line) -> dict[str, object]:
    return {
        "source": line.source.value,
        "x0_mm": round(line.x0, 1),
        "x1_mm": round(line.x1, 1),
        "y_mm": round(line.y, 1),
        **({"anchor": line.anchor} if line.anchor else {}),
    }


def line_data(line: Line | None) -> dict[str, object] | None:
    return _line_data(line) if line is not None else None


def with_lines(layout: PageLayout, extra: Sequence[Line]) -> PageLayout:
    return replace(layout, lines=(*layout.lines, *extra))
