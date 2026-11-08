"""Тело облачного PDF на диск: испорченный файл и сбой своего диска не выдаются за «нет связи»."""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
import pytest
from hse_doc_studio.core.git_remote.client import StudioServerError, StudioServerErrorCode
from hse_doc_studio.infra.git_remote_client.studio_client import _save_stream

PDF = b"%PDF-1.7\ncloud\n%%EOF\n"


def _response(body: bytes, sha256: str) -> httpx.Response:
    return httpx.Response(200, headers={"X-Content-SHA256": sha256, "X-Pages": "2"}, content=body)


async def test__matching_checksum__file_is_saved(tmp_path: Path) -> None:
    dest = tmp_path / "got.part"

    reply = await _save_stream(_response(PDF, hashlib.sha256(PDF).hexdigest()), dest, 1_000)

    assert (reply.size, reply.pages, dest.read_bytes()) == (len(PDF), 2, PDF)


async def test__checksum_mismatch__own_code_and_no_file(tmp_path: Path) -> None:
    dest = tmp_path / "got.part"

    with pytest.raises(StudioServerError) as refused:
        await _save_stream(_response(PDF, "0" * 64), dest, 1_000)

    assert refused.value.code == StudioServerErrorCode.cloud_pdf_checksum
    assert not dest.exists()


async def test__destination_not_writable__write_failed_not_unreachable(tmp_path: Path) -> None:
    occupied = tmp_path / "file"
    occupied.write_text("x")

    with pytest.raises(StudioServerError) as refused:
        await _save_stream(_response(PDF, hashlib.sha256(PDF).hexdigest()), occupied / "got.part", 1_000)

    assert refused.value.code == StudioServerErrorCode.cloud_pdf_write_failed
