"""Загрузка своих файлов в проект: байты без перекодировки, запрещённые пути, предел размера."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.api.config import settings
from httpx import AsyncClient

from tests.factories import project_api_payload

# Все значения байта и последовательности, которые не являются UTF-8: перекодировка в текст их испортила бы.
_BINARY = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) + b"\xff\xfe\x00\x00\xc3\x28"


async def _project(client: AsyncClient, tmp_path: Path) -> tuple[str, Path]:
    folder = tmp_path / "proj"
    folder.mkdir()
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"], folder


async def test__upload__binary_file_is_stored_and_served_byte_for_byte(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, folder = await _project(test_app, tmp_path)

    put = await test_app.put(
        f"/api/v1/projects/{project_id}/files/vkr/images/scheme.png",
        content=_BINARY,
        headers={"Content-Type": "image/png"},
    )

    assert put.status_code == 204, put.text
    assert (folder / "vkr" / "images" / "scheme.png").read_bytes() == _BINARY
    got = await test_app.get(f"/api/v1/projects/{project_id}/files/vkr/images/scheme.png")
    assert got.status_code == 200
    assert got.content == _BINARY
    assert got.headers["content-type"] == "image/png"


async def test__upload__name_with_spaces_and_url_symbols(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, folder = await _project(test_app, tmp_path)

    encoded = "%D1%80%D0%B8%D1%81%201%20%23a%3F.pdf"  # «рис 1 #a?.pdf»
    put = await test_app.put(f"/api/v1/projects/{project_id}/files/refs/{encoded}", content=b"x")

    assert put.status_code == 204, put.text
    assert (folder / "refs" / "рис 1 #a?.pdf").read_bytes() == b"x"


@pytest.mark.parametrize(
    "tail",
    [
        "%2E%2E/escape.png",
        "vkr/%2E%2E/%2E%2E/escape.png",
        ".hse-studio/project.json",
        ".HSE-STUDIO/forms/x.json",
        ".git/hooks/pre-commit",
        "vkr/.build/vkr.aux",
        "bad%5Cname.tex",
    ],
)
async def test__upload__forbidden_path__400_and_nothing_written(
    test_app: AsyncClient, tmp_path: Path, tail: str
) -> None:
    project_id, folder = await _project(test_app, tmp_path)
    before = (folder / ".hse-studio" / "project.json").read_bytes()

    resp = await test_app.put(f"/api/v1/projects/{project_id}/files/{tail}", content=b"payload")

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]["code"] == "invalid_file_path"
    assert (folder / ".hse-studio" / "project.json").read_bytes() == before
    assert not (tmp_path / "escape.png").exists()
    assert not (folder / ".git").exists()


async def test__upload__over_the_file_limit__413_before_writing(
    test_app: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, folder = await _project(test_app, tmp_path)
    monkeypatch.setattr(settings.server, "project_file_max_bytes", 10)

    resp = await test_app.put(f"/api/v1/projects/{project_id}/files/big.bin", content=b"x" * 11)

    assert resp.status_code == 413, resp.text
    body = resp.json()["detail"]
    assert body["code"] == "file_too_large"
    assert body["limit"] == 10
    assert not (folder / "big.bin").exists()


async def test__upload__over_the_limit_without_content_length__413(
    test_app: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, folder = await _project(test_app, tmp_path)
    monkeypatch.setattr(settings.server, "project_file_max_bytes", 10)

    async def chunks():  # type: ignore[no-untyped-def]
        for _ in range(4):
            yield b"xxxx"

    resp = await test_app.put(f"/api/v1/projects/{project_id}/files/big.bin", content=chunks())

    assert resp.status_code == 413, resp.text
    assert not (folder / "big.bin").exists()


async def test__upload__path_taken_by_a_folder__409(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, folder = await _project(test_app, tmp_path)
    (folder / "images").mkdir()
    (folder / "notes.txt").write_bytes(b"x")

    onto_dir = await test_app.put(f"/api/v1/projects/{project_id}/files/images", content=b"x")
    under_file = await test_app.put(f"/api/v1/projects/{project_id}/files/notes.txt/a.png", content=b"x")

    assert onto_dir.status_code == 409, onto_dir.text
    assert onto_dir.json()["detail"]["code"] == "path_conflict"
    assert under_file.status_code == 409, under_file.text
    assert (folder / "notes.txt").read_bytes() == b"x"


async def test__project__reports_the_file_limit_for_the_client(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project(test_app, tmp_path)

    resp = await test_app.get(f"/api/v1/projects/{project_id}")

    assert resp.json()["file_max_bytes"] == settings.server.project_file_max_bytes
