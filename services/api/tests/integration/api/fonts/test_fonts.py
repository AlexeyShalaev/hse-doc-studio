from __future__ import annotations

import pytest
from httpx import AsyncClient

# Plain bytes with a font extension is all UploadFontUC/LocalFontStore require
# (no header-byte validation) — mirrors tests/unit/infra/fonts/test_font_store.py.
_FONT_BYTES = b"FONTDATA"


async def test__list_fonts__no_fonts_uploaded__returns_empty_list(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/fonts")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"fonts": []}


async def test__fonts_crud__upload_list_get_file_delete__full_round_trip(test_app: AsyncClient) -> None:
    upload = await test_app.put("/api/v1/fonts/roundtrip.ttf", content=_FONT_BYTES)
    assert upload.status_code == 200, upload.text
    assert upload.json() == {"name": "roundtrip.ttf", "size_bytes": len(_FONT_BYTES), "family": ""}

    listed = await test_app.get("/api/v1/fonts")
    assert listed.status_code == 200
    assert listed.json() == {"fonts": [{"name": "roundtrip.ttf", "size_bytes": len(_FONT_BYTES), "family": ""}]}

    fetched = await test_app.get("/api/v1/fonts/roundtrip.ttf/file")
    assert fetched.status_code == 200
    assert fetched.content == _FONT_BYTES
    assert fetched.headers["content-type"] == "font/ttf"

    deleted = await test_app.delete("/api/v1/fonts/roundtrip.ttf")
    assert deleted.status_code == 204

    listed_after = await test_app.get("/api/v1/fonts")
    assert listed_after.json() == {"fonts": []}

    fetched_after = await test_app.get("/api/v1/fonts/roundtrip.ttf/file")
    assert fetched_after.status_code == 404


@pytest.mark.parametrize(
    ("filename", "content"),
    [
        pytest.param("malware.exe", b"x", id="unsupported_extension"),
        pytest.param("empty.ttf", b"", id="empty_body"),
    ],
)
async def test__upload_font__invalid_input__returns_400(test_app: AsyncClient, filename: str, content: bytes) -> None:
    resp = await test_app.put(f"/api/v1/fonts/{filename}", content=content)

    assert resp.status_code == 400, resp.text


async def test__get_font_file__unknown_filename__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/fonts/ghost.ttf/file")

    assert resp.status_code == 404, resp.text


async def test__delete_font__unknown_filename__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.delete("/api/v1/fonts/ghost.ttf")

    assert resp.status_code == 404, resp.text
