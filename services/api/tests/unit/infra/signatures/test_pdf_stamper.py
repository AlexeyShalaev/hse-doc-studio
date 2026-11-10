"""Штамповщик PDF: метка, которую не удалось нанести, роняет вызов, и файл не пишется."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.signatures.errors import StampImageError, StampingError, StampPageMissingError
from hse_doc_studio.core.signatures.stamps import Stamp, stamps_digest
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper
from pypdf import PageObject, PdfReader
from pytest_mock import MockerFixture
from reportlab.pdfgen import canvas

_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture(autouse=True)
def _russian_interface() -> None:
    set_interface_language("ru")


def _pdf(path: Path, pages: int = 1) -> Path:
    c = canvas.Canvas(str(path))
    for n in range(pages):
        c.drawString(50, 50, f"body {n + 1}")
        c.showPage()
    c.save()
    return path


def _picture(png: Path, *, page: int = 1, slot_id: str | None = "author") -> Stamp:
    return Stamp(
        page=page,
        x_mm=20,
        y_mm=30,
        width_mm=40,
        png_path=png,
        aspect_ratio=0.4,
        date_text="12.05.2026",
        slot_id=slot_id,
    )


def _images_on(pdf: Path, page: int = 0) -> int:
    resources = PdfReader(str(pdf)).pages[page]["/Resources"]
    xobjects = resources.get("/XObject", {}) if resources else {}
    return sum(1 for ref in xobjects.values() if ref.get_object().get("/Subtype") == "/Image")


def test_picture_and_date_are_stamped(tmp_path: Path) -> None:
    png = tmp_path / "author.png"
    png.write_bytes(_PNG_1PX)
    out = tmp_path / "out.pdf"

    PdfStamper().stamp(_pdf(tmp_path / "in.pdf"), out, [_picture(png)])

    assert _images_on(out) == 1
    text = PdfReader(io.BytesIO(out.read_bytes())).pages[0].extract_text()
    assert "12.05.2026" in text
    assert not out.with_name("out.pdf.part").exists()


def test_broken_png__raises_naming_the_slot_and_writes_nothing(tmp_path: Path) -> None:
    png = tmp_path / "supervisor.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
    out = tmp_path / "out.pdf"

    with pytest.raises(StampImageError) as caught:
        PdfStamper().stamp(_pdf(tmp_path / "in.pdf"), out, [_picture(png, slot_id="supervisor")])

    assert caught.value.slot_id == "supervisor"
    assert caught.value.page == 1
    assert "«supervisor»" in str(caught.value)
    assert "Загрузите картинку подписи заново" in str(caught.value)
    assert not out.exists()
    assert not out.with_name("out.pdf.part").exists()


def test_broken_png_without_slot_id__slot_comes_from_the_file_name(tmp_path: Path) -> None:
    """Пакет сдачи собирает метки из проводной копии без слота: слот берется из имени картинки."""
    png = tmp_path / "author.png"
    png.write_bytes(b"not a png")

    with pytest.raises(StampImageError) as caught:
        PdfStamper().stamp(_pdf(tmp_path / "in.pdf"), tmp_path / "out.pdf", [_picture(png, slot_id=None)])

    assert caught.value.slot_id == "author"


def test_broken_png__english_interface__english_text(tmp_path: Path) -> None:
    set_interface_language("en")
    png = tmp_path / "author.png"
    png.write_bytes(b"not a png")

    with pytest.raises(StampImageError, match="Upload the signature image again"):
        PdfStamper().stamp(_pdf(tmp_path / "in.pdf"), tmp_path / "out.pdf", [_picture(png)])


def test_merge_failure__raises_and_leaves_the_previous_output_untouched(tmp_path: Path, mocker: MockerFixture) -> None:
    png = tmp_path / "author.png"
    png.write_bytes(_PNG_1PX)
    out = tmp_path / "out.pdf"
    out.write_bytes(b"previous")
    mocker.patch.object(PageObject, "merge_page", side_effect=RuntimeError("content stream is read-only"))

    with pytest.raises(StampingError) as caught:
        PdfStamper().stamp(_pdf(tmp_path / "in.pdf"), out, [_picture(png)])

    assert not isinstance(caught.value, StampImageError)
    assert caught.value.page == 1
    assert caught.value.slot_id == "author"
    assert "content stream is read-only" in caught.value.cause
    assert "страницу 1" in str(caught.value)
    assert out.read_bytes() == b"previous"
    assert not out.with_name("out.pdf.part").exists()


def test_merge_failure_of_a_text_plate__raises(tmp_path: Path, mocker: MockerFixture) -> None:
    plate = Stamp(page=1, x_mm=20, y_mm=30, width_mm=70, png_path=None, aspect_ratio=0.4, text="Подписано")
    out = tmp_path / "out.pdf"
    mocker.patch.object(PageObject, "merge_page", side_effect=RuntimeError("boom"))

    with pytest.raises(StampingError):
        PdfStamper().stamp(_pdf(tmp_path / "in.pdf"), out, [plate])

    assert not out.exists()


def test_stamp_on_a_missing_page__raises_instead_of_skipping(tmp_path: Path) -> None:
    png = tmp_path / "author.png"
    png.write_bytes(_PNG_1PX)
    out = tmp_path / "out.pdf"

    with pytest.raises(StampPageMissingError) as caught:
        PdfStamper().stamp(_pdf(tmp_path / "in.pdf", pages=2), out, [_picture(png, page=3)])

    assert caught.value.page == 3
    assert caught.value.slot_id == "author"
    assert "страниц: 2" in str(caught.value)
    assert not out.exists()


def test_no_stamps__copies_the_source(tmp_path: Path) -> None:
    src = _pdf(tmp_path / "in.pdf")
    out = tmp_path / "out.pdf"

    PdfStamper().stamp(src, out, [])

    assert out.read_bytes() == src.read_bytes()


def test_slot_id_stays_out_of_the_visible_layer_fingerprint(tmp_path: Path) -> None:
    png = tmp_path / "author.png"
    with_slot = _picture(png, slot_id="author")
    without_slot = _picture(png, slot_id=None)

    assert with_slot == without_slot
    assert repr(with_slot) == repr(without_slot)
    assert stamps_digest([with_slot], tmp_path) == stamps_digest([without_slot], tmp_path)
