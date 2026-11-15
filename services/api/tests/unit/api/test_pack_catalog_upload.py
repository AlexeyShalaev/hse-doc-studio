"""Приём архива источника потоком: предел по `Content-Length` и по фактически принятым байтам, пустое тело."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import Request
from hse_doc_studio.api.pack_catalog_upload import receive_archive
from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode


def _request(chunks: list[bytes], *, length: int | None = None) -> Request:
    messages = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
    headers = [] if length is None else [(b"content-length", str(length).encode())]

    async def receive() -> dict[str, object]:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    return Request({"type": "http", "method": "POST", "path": "/", "headers": headers}, receive)  # type: ignore[arg-type]


async def test__receive__writes_the_body(tmp_path: Path) -> None:
    target = await receive_archive(_request([b"ab", b"cd"]), tmp_path / "a.part", max_bytes=10)

    assert target.read_bytes() == b"abcd"


@pytest.mark.parametrize(
    ("chunks", "length", "code"),
    [
        ([b"x" * 5, b"x" * 6], None, CatalogErrorCode.archive_too_large),
        ([b"x"], 11, CatalogErrorCode.archive_too_large),
        ([b""], None, CatalogErrorCode.archive_invalid),
    ],
)
async def test__receive__refuses_and_leaves_nothing(
    tmp_path: Path, chunks: list[bytes], length: int | None, code: CatalogErrorCode
) -> None:
    with pytest.raises(CatalogError) as exc:
        await receive_archive(_request(chunks, length=length), tmp_path / "a.part", max_bytes=10)

    assert exc.value.code is code
    assert not (tmp_path / "a.part").exists()
