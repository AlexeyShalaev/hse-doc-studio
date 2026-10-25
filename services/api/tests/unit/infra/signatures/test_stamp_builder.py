from __future__ import annotations

import io
from pathlib import Path

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.value_objects import SignaturePlacement, SignatureSlot, SignaturesState
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper, text_mark_height_mm
from hse_doc_studio.infra.signatures.stamp_builder import detached_caption, stamps_for_doc
from pypdf import PdfReader
from reportlab.pdfgen import canvas


def _state(sign_mode: SignMode, *, enabled: bool = True, date: str | None = None) -> SignaturesState:
    return SignaturesState(
        slots={"sup": SignatureSlot(png_path=None, natural_width_px=None, natural_height_px=None, sign_mode=sign_mode)},
        placements={
            "doc": {"sup": SignaturePlacement(enabled=enabled, page=1, x_mm=20, y_mm=30, width_mm=70, sign_date=date)}
        },
    )


def test_detached_text_slot_becomes_a_caption_stamp(tmp_path: Path) -> None:
    [stamp] = stamps_for_doc(_state(SignMode.detached_text, date="2026-05-12"), "doc", tmp_path, "ru")
    assert stamp.text == detached_caption("ru")
    assert stamp.png_path is None
    assert stamp.date_text == "12.05.2026"


def test_english_caption_for_english_projects(tmp_path: Path) -> None:
    [stamp] = stamps_for_doc(_state(SignMode.detached_text), "doc", tmp_path, "en")
    assert stamp.text == "Signed with a detached electronic signature"


def test_disabled_or_pictureless_slots_are_skipped(tmp_path: Path) -> None:
    assert stamps_for_doc(_state(SignMode.detached_text, enabled=False), "doc", tmp_path, "ru") == []
    assert stamps_for_doc(_state(SignMode.image), "doc", tmp_path, "ru") == []


def test_slot_filter(tmp_path: Path) -> None:
    assert stamps_for_doc(_state(SignMode.detached_text), "doc", tmp_path, "ru", slot_ids=["other"]) == []


def test_caption_is_drawn_with_cyrillic_text(tmp_path: Path) -> None:
    src = tmp_path / "in.pdf"
    c = canvas.Canvas(str(src))
    c.drawString(50, 50, "body")
    c.save()
    out = tmp_path / "out.pdf"
    stamps = stamps_for_doc(_state(SignMode.detached_text), "doc", tmp_path, "ru")

    PdfStamper().stamp(src, out, stamps)

    text = PdfReader(io.BytesIO(out.read_bytes())).pages[0].extract_text().replace("\n", " ")
    assert "Подписано с помощью открепленной электронной подписи" in text


def test_text_mark_height_grows_with_a_narrower_box() -> None:
    caption = detached_caption("ru")
    assert text_mark_height_mm(caption, 40) > text_mark_height_mm(caption, 120)
    assert text_mark_height_mm(caption, 70, "12.05.2026") > text_mark_height_mm(caption, 70)
