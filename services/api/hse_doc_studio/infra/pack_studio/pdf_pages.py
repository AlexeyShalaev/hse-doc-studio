"""Страницы PDF предпросмотра для мест подписей (pack-studio-mcp.md, 4.5): `pypdfium2` и Pillow.

Реализация порта `IPdfPages`: текстовый слой со знаками и их рамками, отрезки рисунка, рамки картинок, доля «чернил»
под рамкой и картинка страницы с нарисованными поверх рамками мест. PDFium не потокобезопасен, поэтому все вызовы
под одним замком. Импорт `pypdfium2` ленивый: модуль грузится только при первом вызове.
"""

from __future__ import annotations

import io
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from PIL import Image, ImageDraw, ImageFont

from hse_doc_studio.core.pack_studio.protocols import Mark, MarkKind
from hse_doc_studio.core.pack_studio.sign_check import (
    Glyph,
    Line,
    LineSource,
    PageLayout,
    Rect,
    is_caption,
    is_sign_line,
    underscore_lines,
    words_of,
)

if TYPE_CHECKING:
    import pypdfium2

_MM_PER_PT: Final = 25.4 / 72
_LOCK = threading.Lock()
_FONT: Final = Path(__file__).resolve().parents[1] / "signatures" / "fonts" / "DejaVuSans.ttf"
# Белым считается пиксель светлее этого (0..255 по яркости).
_WHITE: Final = 200
# Строка пикселей тёмная больше чем на эту долю: это линия, а не рисунок.
_LINE_ROW: Final = 0.5
_MAX_PNG_SIDE: Final = 1600

_COLORS: Final = {
    MarkKind.sign: (31, 111, 235),
    MarkKind.date: (26, 127, 55),
    MarkKind.anchor: (209, 107, 0),
    MarkKind.suggested: (191, 57, 137),
    MarkKind.problem: (207, 34, 46),
}

_PATH_TYPE: Final = 2
_IMAGE_TYPE: Final = 3


@contextmanager
def _document(data: bytes) -> Iterator[pypdfium2.PdfDocument]:
    import pypdfium2  # noqa: PLC0415 — тяжёлый импорт только по месту

    with _LOCK:
        pdf = pypdfium2.PdfDocument(data)
        try:
            yield pdf
        finally:
            pdf.close()


def _rect(bounds: tuple[float, float, float, float], height_pt: float) -> Rect:
    left, bottom, right, top = bounds
    return Rect(
        left * _MM_PER_PT, (height_pt - top) * _MM_PER_PT, right * _MM_PER_PT, (height_pt - bottom) * _MM_PER_PT
    )


def _layout(page: Any, number: int) -> PageLayout:
    width_pt, height_pt = page.get_size()
    text = page.get_textpage()
    try:
        glyphs: list[Glyph] = []
        for i in range(text.count_chars()):
            char = text.get_text_range(i, 1)
            glyphs.append(Glyph(char, _rect(text.get_charbox(i, loose=False), height_pt)))
    finally:
        text.close()
    lines: list[Line] = []
    images: list[Rect] = []
    width_mm = width_pt * _MM_PER_PT
    for obj in page.get_objects():
        if obj.type not in (_PATH_TYPE, _IMAGE_TYPE):
            continue
        rect = _rect(obj.get_bounds(), height_pt)
        if obj.type == _IMAGE_TYPE:
            images.append(rect)
        elif is_sign_line(rect, width_mm):
            lines.append(Line(rect.x0, rect.x1, rect.cy, LineSource.drawing))
    words = words_of(glyphs)
    return PageLayout(
        page=number,
        width_mm=width_mm,
        height_mm=height_pt * _MM_PER_PT,
        glyphs=tuple(glyphs),
        words=words,
        lines=(*lines, *underscore_lines(words)),
        images=tuple(images),
    )


def _render(page: Any, dpi: int) -> Image.Image:
    image: Image.Image = page.render(scale=dpi / 72).to_pil()
    return image.convert("RGB")


def _px(rect: Rect, dpi: int) -> tuple[int, int, int, int]:
    k = dpi / 25.4
    return round(rect.x0 * k), round(rect.y0 * k), round(rect.x1 * k), round(rect.y1 * k)


def _ink(image: Image.Image, rect: Rect, dpi: int, blank: Sequence[Rect]) -> float:
    """Доля тёмных пикселей под рамкой без линий (тёмных строк) и закрашенных `blank` (подписи у линии)."""
    gray = image.convert("L")
    draw = ImageDraw.Draw(gray)
    for item in blank:
        draw.rectangle(_px(item, dpi), fill=255)
    x0, y0, x1, y1 = _px(rect, dpi)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(gray.width, x1), min(gray.height, y1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    crop = gray.crop((x0, y0, x1, y1))
    width = crop.width
    data = crop.tobytes()
    dark = 0
    total = 0
    for row in range(crop.height):
        line = data[row * width : (row + 1) * width]
        row_dark = sum(1 for v in line if v < _WHITE)
        total += width
        if row_dark <= width * _LINE_ROW:
            dark += row_dark
    return dark / total if total else 0.0


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(_FONT), size)
    except OSError:
        return ImageFont.load_default()


def _draw(image: Image.Image, marks: Sequence[Mark], dpi: int) -> Image.Image:
    base = image.convert("RGBA")
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    font = _font(max(10, dpi // 7))
    for mark in marks:
        color = _COLORS[mark.kind]
        box = _px(mark.rect, dpi)
        if mark.kind is MarkKind.anchor:
            x0, y0, x1, _ = box
            for x in range(x0, x1, 8):
                draw.line([(x, y0), (min(x + 4, x1), y0)], fill=(*color, 255), width=2)
        else:
            fill = (*color, 40) if mark.kind is not MarkKind.suggested else (*color, 0)
            draw.rectangle(box, outline=(*color, 255), width=2, fill=fill)
        if mark.label and mark.kind is not MarkKind.anchor:
            _label(draw, font, box, mark.label, (*color, 255), base.width)
    return Image.alpha_composite(base, layer).convert("RGB")


def _label(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    box: tuple[int, int, int, int],
    text: str,
    color: tuple[int, int, int, int],
    width: int,
) -> None:
    """Подпись над рамкой; не влезает справа: сдвигается влево, не влезает сверху: под рамку."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    w, h = right - left, bottom - top
    x = max(0, min(box[0], width - w - 2))
    y = box[1] - h - 4 if box[1] - h - 4 >= 0 else box[3] + 2
    draw.rectangle((x - 1, y - 1, x + w + 1, y + h + 3), fill=(255, 255, 255, 150))
    draw.text((x, y - top), text, fill=color, font=font)


class PdfPages:
    """`IPdfPages` на `pypdfium2`."""

    def page_count(self, data: bytes) -> int:
        with _document(data) as pdf:
            return len(pdf)

    def layouts(self, data: bytes, pages: Sequence[int]) -> dict[int, PageLayout]:
        found: dict[int, PageLayout] = {}
        with _document(data) as pdf:
            for number in pages:
                if 1 <= number <= len(pdf):
                    page = pdf[number - 1]
                    try:
                        found[number] = _layout(page, number)
                    finally:
                        page.close()
        return found

    def ink(self, data: bytes, boxes: Sequence[tuple[int, Rect, Sequence[Rect]]], dpi: int) -> list[float | None]:
        shares: list[float | None] = []
        cache: dict[int, Image.Image] = {}
        with _document(data) as pdf:
            for number, rect, blank in boxes:
                if not 1 <= number <= len(pdf):
                    shares.append(None)
                    continue
                if number not in cache:
                    page = pdf[number - 1]
                    try:
                        cache[number] = _render(page, dpi)
                    finally:
                        page.close()
                shares.append(_ink(cache[number], rect, dpi, blank))
        return shares

    def render(self, data: bytes, page: int, dpi: int, marks: Sequence[Mark]) -> bytes:
        with _document(data) as pdf:
            source = pdf[page - 1]
            try:
                image = _render(source, dpi)
            finally:
                source.close()
        image = _draw(image, marks, dpi)
        if max(image.size) > _MAX_PNG_SIDE:
            image.thumbnail((_MAX_PNG_SIDE, _MAX_PNG_SIDE))
        out = io.BytesIO()
        image.save(out, format="PNG", optimize=True)
        return out.getvalue()


def caption_rects(layout: PageLayout) -> list[Rect]:
    """Подписи у линий («(подпись)», «М.П.»): их можно накрывать, при подсчёте чернил они закрашиваются."""
    return [w.rect for w in layout.words if is_caption(w.text)]
