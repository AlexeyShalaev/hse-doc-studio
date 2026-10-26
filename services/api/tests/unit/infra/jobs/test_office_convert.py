"""convert_office_to_sibling и OfficeConvertHandler."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.files import ArtifactRef, ManifestFile
from hse_doc_studio.core.jobs.office import (
    REASON_CONVERTER_UNAVAILABLE,
    REASON_NOT_CONVERTIBLE,
    REASON_WRITE_FAILED,
    OfficeConvertPayload,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.core.jobs.protocols import JobContext
from hse_doc_studio.infra.jobs.office_convert import OfficeConvertHandler, convert_office_to_sibling
from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs
from pypdf import PdfWriter

from tests.unit.core.jobs.samples import JOB_ID, PROJECT_ID


def _pdf_bytes(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _converter(result: bytes | None | BaseException) -> MagicMock:
    converter = MagicMock()
    if isinstance(result, BaseException):
        converter.convert_to_pdf = AsyncMock(side_effect=result)
    else:
        converter.convert_to_pdf = AsyncMock(return_value=result)
    return converter


async def _convert(
    converter: MagicMock,
    workspace: Path,
    *,
    source: str = "tz/_custom/ТЗ.docx",
    output: str = "tz/_custom/ТЗ.pdf",
    image: str | None = None,
    want_pages: bool = False,
    outputs: LocalJobOutputs | None = None,
) -> OfficeConvertResult:
    return await convert_office_to_sibling(
        converter, outputs or LocalJobOutputs(), workspace, source, output, image, want_pages
    )


@pytest.mark.unit
async def test__convert_office_to_sibling__ok__sibling_written_sha_size_pages_only_when_wanted(tmp_path: Path) -> None:
    pdf = _pdf_bytes(3)
    converter = _converter(pdf)

    plain = await _convert(converter, tmp_path)
    with_pages = await _convert(converter, tmp_path, want_pages=True)

    assert (tmp_path / "tz/_custom/ТЗ.pdf").read_bytes() == pdf
    assert plain.status is OfficeConvertStatus.ok
    assert plain.pages is None
    assert plain.output == ArtifactRef("tz/_custom/ТЗ.pdf", hashlib.sha256(pdf).hexdigest(), len(pdf))
    assert with_pages.pages == 3
    assert with_pages.output == plain.output


@pytest.mark.unit
async def test__convert_office_to_sibling__image_none_calls_converter_without_image(tmp_path: Path) -> None:
    converter = _converter(b"%PDF")

    await _convert(converter, tmp_path, image=None)
    await _convert(converter, tmp_path, image="gotenberg/gotenberg:8.1")

    first, second = converter.convert_to_pdf.await_args_list
    assert first.args == (tmp_path / "tz/_custom/ТЗ.docx",)
    assert first.kwargs == {}
    assert second.args == (tmp_path / "tz/_custom/ТЗ.docx",)
    assert second.kwargs == {"image": "gotenberg/gotenberg:8.1"}


@pytest.mark.unit
async def test__convert_office_to_sibling__page_count_failure__pages_none(tmp_path: Path) -> None:
    result = await _convert(_converter(b"not a pdf"), tmp_path, want_pages=True)

    assert result.status is OfficeConvertStatus.ok
    assert result.pages is None


@pytest.mark.unit
async def test__convert_office_to_sibling__converter_none__unavailable_no_file(tmp_path: Path) -> None:
    result = await _convert(_converter(None), tmp_path)

    assert result == OfficeConvertResult(
        status=OfficeConvertStatus.unavailable, reason_code=REASON_CONVERTER_UNAVAILABLE
    )
    assert not (tmp_path / "tz").exists()


@pytest.mark.unit
async def test__convert_office_to_sibling__write_oserror__unavailable_with_detail(tmp_path: Path) -> None:
    outputs = MagicMock()
    outputs.write_output.side_effect = OSError("disk full")

    result = await _convert(_converter(b"%PDF"), tmp_path, outputs=outputs)

    assert result.status is OfficeConvertStatus.unavailable
    assert result.reason_code == REASON_WRITE_FAILED
    assert result.detail == "disk full"
    assert result.output is None


@pytest.mark.unit
async def test__convert_office_to_sibling__symlink_dir_outside_workspace__write_failed_not_raised(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / "slides").symlink_to(outside, target_is_directory=True)

    result = await _convert(_converter(b"%PDF"), workspace, source="slides/a.pptx", output="slides/a.pdf")

    assert result.status is OfficeConvertStatus.unavailable
    assert result.reason_code == REASON_WRITE_FAILED
    assert "escapes" in result.detail
    assert list(outside.iterdir()) == []


@pytest.mark.unit
async def test__convert_office_to_sibling__backslash_in_name__write_failed_not_raised(tmp_path: Path) -> None:
    result = await _convert(_converter(b"%PDF"), tmp_path, source="custom/my\\deck.pptx", output="custom/my\\deck.pdf")

    assert result.status is OfficeConvertStatus.unavailable
    assert result.reason_code == REASON_WRITE_FAILED
    assert "backslash" in result.detail


@pytest.mark.unit
async def test__convert_office_to_sibling__converter_raises__propagates(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        await _convert(_converter(RuntimeError("boom")), tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize("source", ["tz/a.pdf", "tz/a.zip", "tz/a", "tz/a.tex"])
async def test__convert_office_to_sibling__non_convertible_ext__unavailable_without_call(
    tmp_path: Path, source: str
) -> None:
    converter = _converter(b"%PDF")

    result = await _convert(converter, tmp_path, source=source, output="tz/a.out.pdf")

    assert result == OfficeConvertResult(status=OfficeConvertStatus.unavailable, reason_code=REASON_NOT_CONVERTIBLE)
    converter.convert_to_pdf.assert_not_called()


@pytest.mark.unit
async def test__convert_office_to_sibling__upper_case_ext__converted(tmp_path: Path) -> None:
    converter = _converter(b"%PDF")

    result = await _convert(converter, tmp_path, source="tz/ТЗ.DOCX", output="tz/ТЗ.pdf")

    assert result.status is OfficeConvertStatus.ok
    converter.convert_to_pdf.assert_awaited_once()


def _ctx(workspace: Path) -> JobContext:
    return JobContext(
        job_id=JOB_ID,
        project_id=PROJECT_ID,
        actor=Actor.local(),
        locale=Lang.ru,
        workspace=workspace,
        outputs=LocalJobOutputs(),
    )


@pytest.mark.unit
async def test__office_convert_handler__converts_through_payload_and_context(tmp_path: Path) -> None:
    pdf = _pdf_bytes(2)
    converter = _converter(pdf)
    payload = OfficeConvertPayload(
        source=ManifestFile("deck/slides.pptx"),
        output_path="deck/slides.pdf",
        image="gotenberg/gotenberg:8.1",
        want_pages=True,
    )

    result = await OfficeConvertHandler(converter).handle(payload, _ctx(tmp_path))

    assert isinstance(result, OfficeConvertResult)
    assert result.status is OfficeConvertStatus.ok
    assert result.pages == 2
    assert (tmp_path / "deck/slides.pdf").read_bytes() == pdf
    converter.convert_to_pdf.assert_awaited_once_with(tmp_path / "deck/slides.pptx", image="gotenberg/gotenberg:8.1")


@pytest.mark.unit
async def test__office_convert_handler__converter_none__unavailable(tmp_path: Path) -> None:
    payload = OfficeConvertPayload(source=ManifestFile("a.docx"), output_path="a.pdf")

    result = await OfficeConvertHandler(_converter(None)).handle(payload, _ctx(tmp_path))

    assert isinstance(result, OfficeConvertResult)
    assert result.status is OfficeConvertStatus.unavailable
