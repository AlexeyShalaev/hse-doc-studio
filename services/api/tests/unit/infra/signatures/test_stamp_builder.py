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


def test_plate_rows_from_signer_like_the_hse_stamp(tmp_path: Path) -> None:
    from hse_doc_studio.core.value_objects import SignerInfo  # noqa: PLC0415
    from hse_doc_studio.infra.signatures.stamp_builder import signer_details  # noqa: PLC0415

    signer = SignerInfo(
        kind="x509",
        owner="Кротов Владимир Николаевич",
        cert_id="20B29A0033B4B8B34035055AE363F2E9",
        valid_from="2026-04-21T09:13:14+00:00",
        valid_to="2027-04-21T09:23:14+00:00",
    )
    rows = dict(signer_details(signer, "ru"))
    assert rows["Сертификат"] == "20B29A0033B4B8B34035055AE363F2E9"
    assert rows["Владелец"] == "Кротов Владимир Николаевич"
    assert rows["Действителен"] == "с 21.04.2026 по 21.04.2027"
    assert dict(signer_details(signer, "en"))["Valid"] == "from 21.04.2026 to 21.04.2027"
    assert signer_details(None, "ru") == ()

    src = tmp_path / "in.pdf"
    c = canvas.Canvas(str(src))
    c.drawString(50, 50, "body")
    c.save()
    state = _state(SignMode.detached_text, date="2026-09-17")
    slot = state.slots["sup"]
    state = SignaturesState(
        slots={"sup": SignatureSlot(None, None, None, sign_mode=slot.sign_mode, signer=signer)},
        placements=state.placements,
    )
    out = tmp_path / "out.pdf"
    PdfStamper().stamp(src, out, stamps_for_doc(state, "doc", tmp_path, "ru"))
    text = PdfReader(io.BytesIO(out.read_bytes())).pages[0].extract_text().replace("\n", " ")
    assert "Кротов Владимир Николаевич" in text
    assert "Дата подписания: 17.09.2026" in text


def test_stamps_digest_changes_with_signer(tmp_path: Path) -> None:
    from hse_doc_studio.core.value_objects import SignerInfo  # noqa: PLC0415
    from hse_doc_studio.infra.signatures.stamp_builder import stamps_digest  # noqa: PLC0415

    base = _state(SignMode.detached_text)
    a = stamps_digest(stamps_for_doc(base, "doc", tmp_path, "ru"))
    with_signer = SignaturesState(
        slots={
            "sup": SignatureSlot(None, None, None, sign_mode=SignMode.detached_text, signer=SignerInfo("manual", "X"))
        },
        placements=base.placements,
    )
    assert a != stamps_digest(stamps_for_doc(with_signer, "doc", tmp_path, "ru"))
    assert a == stamps_digest(stamps_for_doc(base, "doc", tmp_path, "ru"))
