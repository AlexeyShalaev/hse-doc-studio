from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.infra.pdf.extract import extract_pdf_text
from hse_doc_studio.use_cases.chat.tools.read_pdf import ReadPdfTool, _parse_pages
from pypdf import PdfWriter


def _blank_pdf(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _ctx() -> AgentToolContext:
    return cast(AgentToolContext, SimpleNamespace(project_id=uuid4()))


# ── _parse_pages ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test__parse_pages() -> None:
    assert _parse_pages("1-3") == [1, 2, 3]
    assert _parse_pages("5") == [5]
    assert _parse_pages("1,4,7") == [1, 4, 7]
    assert _parse_pages("2-3,6") == [2, 3, 6]
    assert _parse_pages(None) is None
    assert _parse_pages("") is None
    assert _parse_pages("abc") is None


# ── extract_pdf_text ─────────────────────────────────────────────────────


@pytest.mark.unit
def test__extract_pdf_text__counts_pages() -> None:
    text, total = extract_pdf_text(_blank_pdf(2))
    assert total == 2
    assert "Стр. 1" in text
    assert "Стр. 2" in text


@pytest.mark.unit
def test__extract_pdf_text__page_subset() -> None:
    text, total = extract_pdf_text(_blank_pdf(3), pages=[2])
    assert total == 3
    assert "Стр. 2" in text
    assert "Стр. 1" not in text


# ── ReadPdfTool.handle ───────────────────────────────────────────────────


def _tool(content: bytes | None = None, *, raises: type[Exception] | None = None) -> ReadPdfTool:
    get_file = SimpleNamespace()

    async def _execute(_inp: object) -> object:
        if raises is not None:
            raise raises()
        return SimpleNamespace(content=content)

    get_file.execute = _execute  # type: ignore[attr-defined]
    return ReadPdfTool(cast("object", get_file))  # type: ignore[arg-type]


@pytest.mark.unit
async def test__read_pdf__missing_path__error() -> None:
    res = await _tool().handle(_ctx(), {})
    assert res.is_error


@pytest.mark.unit
async def test__read_pdf__non_pdf_path__error() -> None:
    res = await _tool().handle(_ctx(), {"path": "vkr/vkr.tex"})
    assert res.is_error
    assert "read_tex" in res.text


@pytest.mark.unit
async def test__read_pdf__not_found__error() -> None:
    res = await _tool(raises=FileNotFoundError).handle(_ctx(), {"path": "vkr/vkr.pdf"})
    assert res.is_error
    assert "не найден" in res.text


@pytest.mark.unit
async def test__read_pdf__success__reports_pages() -> None:
    res = await _tool(_blank_pdf(2)).handle(_ctx(), {"path": "vkr/vkr.pdf"})
    assert not res.is_error
    assert "2 стр." in res.text


@pytest.mark.unit
async def test__read_pdf__corrupt__error() -> None:
    res = await _tool(b"not a pdf at all").handle(_ctx(), {"path": "vkr/vkr.pdf"})
    assert res.is_error
    assert "PDF" in res.text
