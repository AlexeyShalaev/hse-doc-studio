from __future__ import annotations

import io
from collections import defaultdict
from pathlib import Path

import structlog
from pypdf import PdfReader, PdfWriter
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.errors import StampImageError, StampingError, StampPageMissingError
from hse_doc_studio.core.signatures.stamps import Stamp, format_sign_date

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


class PdfStamper:
    """Overlays PNG stamps onto specific pages of a PDF.

    Each stamped page is rebuilt by generating a one-page overlay PDF via
    reportlab at the same MediaBox as the source page and merging it on top
    with pypdf's merge_page. Pages without stamps are copied through
    untouched (no re-encoding, no quality loss). A mark that cannot be placed
    raises `StampingError` instead of being skipped.
    """

    def mark_height_mm(self, stamp: Stamp) -> float:
        """Высота метки на странице (`IMarkMeasure`): картинка по своим пропорциям, плашка по вёрстке её строк."""
        if stamp.text is None:
            return stamp.width_mm * stamp.aspect_ratio
        caption, body = _mark_lines(stamp, _ensure_text_font(), stamp.width_mm * mm)
        return ((len(caption) + len(body)) * _TEXT_SIZE_PT * _TEXT_LEADING + 2 * _TEXT_PAD_PT) / mm

    def stamp(
        self,
        source_pdf: Path,
        output_pdf: Path,
        stamps: list[Stamp],
    ) -> None:
        """Пишет `output_pdf`: `source_pdf` с метками `stamps` поверх страниц.

        Любая метка, которую не удалось нанести (страницы нет, картинка не читается, слой не наложился),
        роняет вызов с `StampingError`, и `output_pdf` не создается и не меняется: PDF без отметки подписи
        не должен уйти ни в фиксацию, ни в печатную копию, ни в пакет.
        """
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
        _require_pages(by_page, len(reader.pages))

        for i, source_page in enumerate(reader.pages):
            page_num = i + 1
            page_stamps = by_page.get(page_num, [])
            # Merge into the writer's own copy of the page: pypdf 7 refuses to
            # rewrite the content stream of a page that has no writer.
            page = writer.add_page(source_page)
            if page_stamps:
                overlay_bytes = self._build_overlay_page(
                    page_width_pt=float(page.mediabox.width),
                    page_height_pt=float(page.mediabox.height),
                    stamps=page_stamps,
                )
                try:
                    page.merge_page(PdfReader(io.BytesIO(overlay_bytes)).pages[0])
                except Exception as exc:
                    logger.exception("pdf_stamper: merge_page failed", page=page_num)
                    raise _merge_failed(page_num, page_stamps, exc) from exc

        _write_atomically(writer, output_pdf)

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
                try:
                    _draw_text_mark(c, s, page_height_pt)
                except Exception as exc:
                    logger.exception("pdf_stamper: text mark failed", page=s.page, slot_id=_slot_of(s))
                    raise _text_mark_failed(s, exc) from exc
                continue
            if s.png_path is not None:
                _draw_picture(c, s, s.png_path, page_height_pt)
        try:
            c.save()
        except Exception as exc:
            page = stamps[0].page
            logger.exception("pdf_stamper: overlay not rendered", page=page)
            raise _merge_failed(page, stamps, exc) from exc
        return buf.getvalue()


def _draw_picture(c: canvas.Canvas, s: Stamp, png_path: Path, page_height_pt: float) -> None:
    width_pt = s.width_mm * mm
    height_pt = width_pt * s.aspect_ratio
    x_pt = s.x_mm * mm
    # UI y is mm-from-top; PDF y is points-from-bottom. We also have to
    # offset by the image's own height since drawImage anchors at the
    # bottom-left of the image, not the top-left.
    y_pdf_pt = page_height_pt - s.y_mm * mm - height_pt
    try:
        c.drawImage(
            str(png_path),
            x_pt,
            y_pdf_pt,
            width=width_pt,
            height=height_pt,
            preserveAspectRatio=True,
            mask="auto",
        )
    except Exception as exc:
        logger.warning(
            "pdf_stamper: drawImage failed", png=str(png_path), page=s.page, slot_id=_slot_of(s), exc=str(exc)
        )
        raise _image_failed(s, exc) from exc
    if s.date_text:
        # Baseline roughly at the vertical middle of the signature so
        # the date sits on the same ruled line as the autograph.
        c.setFont("Helvetica", 10)
        c.drawString(
            x_pt + width_pt + _DATE_GAP_MM * mm,
            y_pdf_pt + height_pt / 2 - _DATE_BASELINE_NUDGE_PT,
            s.date_text,
        )


def _slot_of(s: Stamp) -> str | None:
    """Слот метки: из самой метки, иначе по имени картинки (картинки слотов лежат как `<slot_id>.png`)."""
    if s.slot_id:
        return s.slot_id
    return s.png_path.stem if s.png_path is not None else None


def _slot_part(slot: str | None) -> tuple[str, str]:
    return (f" слота «{slot}»", f" of slot «{slot}»") if slot else ("", "")


def _require_pages(by_page: dict[int, list[Stamp]], total: int) -> None:
    """Метка на странице, которой нет в PDF, не ставится вовсе: это отказ, а не пропуск."""
    for page_num in sorted(by_page):
        if 1 <= page_num <= total:
            continue
        slot = _slot_of(by_page[page_num][0])
        ru_slot, en_slot = _slot_part(slot)
        logger.warning("pdf_stamper: stamp requested for missing page", requested=page_num, actual_pages=total)
        raise StampPageMissingError(
            localized_error(
                f"Место подписи{ru_slot} стоит на странице {page_num}, а в собранном PDF страниц: {total}. "
                "Передвиньте место подписи на существующую страницу и повторите.",
                f"The signature place{en_slot} is on page {page_num}, but the built PDF has {total} page(s). "
                "Move the signature place to an existing page and try again.",
            ),
            page=page_num,
            slot_id=slot,
        )


def _image_failed(s: Stamp, exc: Exception) -> StampImageError:
    slot = _slot_of(s)
    ru_slot, en_slot = _slot_part(slot)
    return StampImageError(
        localized_error(
            f"Не удалось нанести картинку подписи{ru_slot} на страницу {s.page}: файл картинки поврежден "
            "или это не PNG. Загрузите картинку подписи заново.",
            f"Could not place the signature image{en_slot} on page {s.page}: the image file is damaged "
            "or is not a PNG. Upload the signature image again.",
        ),
        page=s.page,
        slot_id=slot,
        cause=str(exc),
    )


def _text_mark_failed(s: Stamp, exc: Exception) -> StampingError:
    slot = _slot_of(s)
    ru_slot, en_slot = _slot_part(slot)
    return StampingError(
        localized_error(
            f"Не удалось нанести плашку подписи{ru_slot} на страницу {s.page}: {exc}. Файл с подписями не создан.",
            f"Could not place the signature plate{en_slot} on page {s.page}: {exc}. The signed file was not created.",
        ),
        page=s.page,
        slot_id=slot,
        cause=str(exc),
    )


def _merge_failed(page: int, stamps: list[Stamp], exc: Exception) -> StampingError:
    slots = sorted({slot for slot in map(_slot_of, stamps) if slot})
    return StampingError(
        localized_error(
            f"Не удалось наложить отметки подписей на страницу {page}: {exc}. Файл с подписями не создан. "
            "Пересоберите документ и повторите; если ошибка останется, сообщите администратору Студии.",
            f"Could not overlay the signature marks on page {page}: {exc}. The signed file was not created. "
            "Rebuild the document and try again; if the error persists, contact the Studio administrator.",
        ),
        page=page,
        slot_id=slots[0] if len(slots) == 1 else None,
        cause=str(exc),
    )


def _write_atomically(writer: PdfWriter, output_pdf: Path) -> None:
    """Пишет во временный файл рядом и переименовывает: при сбое записи на месте `output_pdf` не остается обрывка."""
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    part = output_pdf.with_name(output_pdf.name + ".part")
    try:
        with part.open("wb") as fh:
            writer.write(fh)
        part.replace(output_pdf)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def _mark_lines(s: Stamp, font: str, width_pt: float) -> tuple[list[str], list[str]]:
    """(caption lines, body lines) of a text mark, wrapped to `width_pt`."""
    inner = width_pt - 2 * _TEXT_PAD_PT
    bold = _TEXT_FONT_BOLD if (s.details or s.subtitle) else font
    caption = simpleSplit(s.text or "", bold, _TEXT_SIZE_PT, inner)
    if s.subtitle:
        caption += simpleSplit(s.subtitle, bold, _TEXT_SIZE_PT, inner)
    body: list[str] = []
    for label, value in s.details:
        body.extend(simpleSplit(f"{label}: {value}", font, _TEXT_SIZE_PT, inner))
    if s.date_text:
        row = f"{s.date_label}: {s.date_text}" if (s.details or s.subtitle) and s.date_label else s.date_text
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
    plate = bool(s.details or s.subtitle)
    c.setLineWidth(1.0 if plate else 0.5)
    c.setStrokeColorRGB(0.35, 0.35, 0.35)
    if plate:
        c.roundRect(x_pt, y_bottom, width_pt, height_pt, _PLATE_RADIUS_PT, stroke=1, fill=0)
    else:
        c.rect(x_pt, y_bottom, width_pt, height_pt, stroke=1, fill=0)
    c.setFillColorRGB(0, 0, 0)
    y = y_bottom + height_pt - _TEXT_PAD_PT - _TEXT_SIZE_PT
    c.setFont(_TEXT_FONT_BOLD if plate else font, _TEXT_SIZE_PT)
    for line in caption:
        c.drawString(x_pt + _TEXT_PAD_PT, y, line)
        y -= line_h
    c.setFont(font, _TEXT_SIZE_PT)
    for line in body:
        c.drawString(x_pt + _TEXT_PAD_PT, y, line)
        y -= line_h


__all__ = ["PdfStamper", "Stamp", "format_sign_date", "text_mark_height_mm"]
