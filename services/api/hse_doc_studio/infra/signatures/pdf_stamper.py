from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import structlog
from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

logger = structlog.get_logger()

# Date text placement relative to the signature image.
_DATE_GAP_MM = 4.0
_DATE_BASELINE_NUDGE_PT = 3.0

# Text marks («Подписано с помощью открепленной электронной подписи») need
# Cyrillic, which the built-in Helvetica lacks — a bundled DejaVu Sans does it.
_TEXT_FONT = "DejaVuSans"
_TEXT_FONT_FILE = Path(__file__).with_name("fonts") / "DejaVuSans.ttf"
_TEXT_FONT_BOLD = "DejaVuSans-Bold"
_TEXT_FONT_BOLD_FILE = Path(__file__).with_name("fonts") / "DejaVuSans-Bold.ttf"
_PLATE_RADIUS_PT = 7.0
_TEXT_SIZE_PT = 8.0
_TEXT_LEADING = 1.25
_TEXT_PAD_PT = 3.0


def _ensure_text_font() -> str:
    registered = pdfmetrics.getRegisteredFontNames()
    if _TEXT_FONT not in registered:
        pdfmetrics.registerFont(TTFont(_TEXT_FONT, str(_TEXT_FONT_FILE)))
    if _TEXT_FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(_TEXT_FONT_BOLD, str(_TEXT_FONT_BOLD_FILE)))
    return _TEXT_FONT


def format_sign_date(iso_date: str | None) -> str | None:
    """ISO «2026-05-12» → печатное «12.05.2026»; None/пусто → None."""
    if not iso_date:
        return None
    try:
        return date.fromisoformat(iso_date).strftime("%d.%m.%Y")
    except ValueError:
        # Свободный формат из старых данных — печатаем как есть.
        return iso_date


@dataclass(frozen=True)
class Stamp:
    """A single PNG or text mark to place on a PDF page.

    Coordinates are in millimetres from the **top-left** corner of the page —
    the natural convention for the UI overlay layer. The stamper handles the
    flip to PDF native coords (bottom-left origin, points) internally so
    callers don't have to think about it.
    """

    page: int  # 1-indexed
    x_mm: float
    y_mm: float
    width_mm: float
    png_path: Path | None
    aspect_ratio: float  # height / width — preserves uploaded PNG proportions
    # Text mark instead of a PNG: a framed, wrapped caption (the date, when
    # set, goes on its own last line inside the frame).
    text: str | None = None
    # Signature plate rows («Сертификат», «Владелец», ...) under the bold caption.
    details: tuple[tuple[str, str], ...] = ()
    # Label of the date row when the plate has details («Дата подписания»).
    date_label: str = ""
    # Signing date rendered as text to the right of the PNG («12.05.2026»).
    # ASCII-only by design so the built-in Helvetica suffices.
    date_text: str | None = None


class PdfStamper:
    """Overlays PNG stamps onto specific pages of a PDF.

    Each stamped page is rebuilt by generating a one-page overlay PDF via
    reportlab at the same MediaBox as the source page and merging it on top
    with pypdf's merge_page. Pages without stamps are copied through
    untouched (no re-encoding, no quality loss).
    """

    def stamp(  # noqa: C901
        self,
        source_pdf: Path,
        output_pdf: Path,
        stamps: list[Stamp],
    ) -> None:
        if not stamps:
            # No-op: caller still expects an output file, so just copy bytes.
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            output_pdf.write_bytes(source_pdf.read_bytes())
            return

        reader = PdfReader(str(source_pdf))
        writer = PdfWriter()

        by_page: dict[int, list[Stamp]] = defaultdict(list)
        for s in stamps:
            by_page[s.page].append(s)

        for i, page in enumerate(reader.pages):
            page_num = i + 1
            page_stamps = by_page.get(page_num, [])
            if page_stamps:
                page_width_pt = float(page.mediabox.width)
                page_height_pt = float(page.mediabox.height)
                overlay_bytes = self._build_overlay_page(
                    page_width_pt=page_width_pt,
                    page_height_pt=page_height_pt,
                    stamps=page_stamps,
                )
                overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
                try:
                    page.merge_page(overlay_reader.pages[0])
                except Exception as exc:
                    logger.warning(
                        "pdf_stamper: merge_page failed",
                        page=page_num,
                        exc=str(exc),
                    )
            writer.add_page(page)

        # Pages requested by stamps but missing from the PDF: log and skip
        # rather than crash. The user's pdf may be shorter than they expect
        # (e.g. title overflowed onto a second page that they didn't realise).
        for page_num in by_page:
            if page_num > len(reader.pages):
                logger.warning(
                    "pdf_stamper: stamp requested for missing page",
                    requested=page_num,
                    actual_pages=len(reader.pages),
                )

        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        with output_pdf.open("wb") as fh:
            writer.write(fh)

    @staticmethod
    def _build_overlay_page(
        page_width_pt: float,
        page_height_pt: float,
        stamps: list[Stamp],
    ) -> bytes:
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=(page_width_pt, page_height_pt))
        for s in stamps:
            if s.text is not None:
                _draw_text_mark(c, s, page_height_pt)
                continue
            if s.png_path is None:
                continue
            width_pt = s.width_mm * mm
            height_pt = width_pt * s.aspect_ratio
            x_pt = s.x_mm * mm
            # UI y is mm-from-top; PDF y is points-from-bottom. We also have to
            # offset by the image's own height since drawImage anchors at the
            # bottom-left of the image, not the top-left.
            y_top_pt = s.y_mm * mm
            y_pdf_pt = page_height_pt - y_top_pt - height_pt
            try:
                c.drawImage(
                    str(s.png_path),
                    x_pt,
                    y_pdf_pt,
                    width=width_pt,
                    height=height_pt,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception as exc:
                logger.warning(
                    "pdf_stamper: drawImage failed",
                    png=str(s.png_path),
                    exc=str(exc),
                )
            if s.date_text:
                # Baseline roughly at the vertical middle of the signature so
                # the date sits on the same ruled line as the autograph.
                c.setFont("Helvetica", 10)
                c.drawString(
                    x_pt + width_pt + _DATE_GAP_MM * mm,
                    y_pdf_pt + height_pt / 2 - _DATE_BASELINE_NUDGE_PT,
                    s.date_text,
                )
        c.save()
        return buf.getvalue()


def _mark_lines(s: Stamp, font: str, width_pt: float) -> tuple[list[str], list[str]]:
    """(caption lines, body lines) of a text mark, wrapped to `width_pt`."""
    inner = width_pt - 2 * _TEXT_PAD_PT
    caption = simpleSplit(s.text or "", _TEXT_FONT_BOLD if s.details else font, _TEXT_SIZE_PT, inner)
    body: list[str] = []
    for label, value in s.details:
        body.extend(simpleSplit(f"{label}: {value}", font, _TEXT_SIZE_PT, inner))
    if s.date_text:
        row = f"{s.date_label}: {s.date_text}" if s.details and s.date_label else s.date_text
        body.append(row)
    return caption, body


def text_mark_height_mm(
    text: str, width_mm: float, date_text: str | None = None, details: tuple[tuple[str, str], ...] = ()
) -> float:
    """Height of the framed text mark, so the UI can size the placement box."""
    font = _ensure_text_font()
    probe = Stamp(
        page=1,
        x_mm=0,
        y_mm=0,
        width_mm=width_mm,
        png_path=None,
        aspect_ratio=0,
        text=text,
        date_text=date_text,
        details=details,
    )
    caption, body = _mark_lines(probe, font, width_mm * mm)
    return ((len(caption) + len(body)) * _TEXT_SIZE_PT * _TEXT_LEADING + 2 * _TEXT_PAD_PT) / mm


def _draw_text_mark(c: canvas.Canvas, s: Stamp, page_height_pt: float) -> None:
    font = _ensure_text_font()
    width_pt = s.width_mm * mm
    caption, body = _mark_lines(s, font, width_pt)
    line_h = _TEXT_SIZE_PT * _TEXT_LEADING
    height_pt = (len(caption) + len(body)) * line_h + 2 * _TEXT_PAD_PT
    x_pt = s.x_mm * mm
    y_bottom = page_height_pt - s.y_mm * mm - height_pt
    c.setLineWidth(0.5 if not s.details else 1.0)
    c.setStrokeColorRGB(0.35, 0.35, 0.35)
    if s.details:
        c.roundRect(x_pt, y_bottom, width_pt, height_pt, _PLATE_RADIUS_PT, stroke=1, fill=0)
    else:
        c.rect(x_pt, y_bottom, width_pt, height_pt, stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)
    y = y_bottom + height_pt - _TEXT_PAD_PT - _TEXT_SIZE_PT
    c.setFont(_TEXT_FONT_BOLD if s.details else font, _TEXT_SIZE_PT)
    for line in caption:
        c.drawString(x_pt + _TEXT_PAD_PT, y, line)
        y -= line_h
    c.setFont(font, _TEXT_SIZE_PT)
    for line in body:
        c.drawString(x_pt + _TEXT_PAD_PT, y, line)
        y -= line_h
