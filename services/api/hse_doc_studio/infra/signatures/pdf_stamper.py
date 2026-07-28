from __future__ import annotations

import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import structlog
from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

logger = structlog.get_logger()

# Date text placement relative to the signature image.
_DATE_GAP_MM = 4.0
_DATE_BASELINE_NUDGE_PT = 3.0


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
    """A single PNG to place on a PDF page.

    Coordinates are in millimetres from the **top-left** corner of the page —
    the natural convention for the UI overlay layer. The stamper handles the
    flip to PDF native coords (bottom-left origin, points) internally so
    callers don't have to think about it.
    """

    page: int  # 1-indexed
    x_mm: float
    y_mm: float
    width_mm: float
    png_path: Path
    aspect_ratio: float  # height / width — preserves uploaded PNG proportions
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
