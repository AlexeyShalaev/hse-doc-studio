"""Правка того же файла снаружи (VS Code) не должна пропадать молча."""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def _project_with_file(test_app: AsyncClient, tmp_path: Path, body: bytes) -> tuple[str, Path]:
    folder = tmp_path / "vkr"
    folder.mkdir()
    resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(folder)))
    project_id = resp.json()["id"]
    target = folder / "notes.tex"
    target.write_bytes(body)
    return project_id, target


async def test__get_file__returns_an_etag_for_the_content(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_file(test_app, tmp_path, b"hello")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/files/notes.tex")

    assert resp.status_code == 200, resp.text
    assert resp.headers["etag"]


async def test__file_version__matches_the_etag_of_the_content(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_file(test_app, tmp_path, b"hello")

    content = await test_app.get(f"/api/v1/projects/{project_id}/files/notes.tex")
    version = await test_app.get(f"/api/v1/projects/{project_id}/file-version/notes.tex")

    assert version.json()["etag"] == content.headers["etag"]
    assert version.json()["size"] == len("hello")


async def test__file_version__changes_after_an_external_edit(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, target = await _project_with_file(test_app, tmp_path, b"hello")
    before = (await test_app.get(f"/api/v1/projects/{project_id}/file-version/notes.tex")).json()["etag"]

    target.write_bytes(b"edited in VS Code")

    after = (await test_app.get(f"/api/v1/projects/{project_id}/file-version/notes.tex")).json()["etag"]
    assert after != before


async def test__put_file__if_match_matches__writes_and_returns_the_new_etag(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_id, target = await _project_with_file(test_app, tmp_path, b"hello")
    etag = (await test_app.get(f"/api/v1/projects/{project_id}/files/notes.tex")).headers["etag"]

    resp = await test_app.put(
        f"/api/v1/projects/{project_id}/files/notes.tex",
        content=b"mine",
        headers={"If-Match": etag, "Content-Type": "text/plain"},
    )

    assert resp.status_code == 204, resp.text
    assert target.read_bytes() == b"mine"
    assert resp.headers["etag"]


async def test__put_file__file_changed_on_disk__refuses_and_returns_the_disk_version(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Ровно тот случай, ради которого всё делалось: правку из VS Code нельзя затереть.
    project_id, target = await _project_with_file(test_app, tmp_path, b"hello")
    stale_etag = (await test_app.get(f"/api/v1/projects/{project_id}/files/notes.tex")).headers["etag"]
    target.write_bytes(b"edited in VS Code")

    resp = await test_app.put(
        f"/api/v1/projects/{project_id}/files/notes.tex",
        content=b"mine",
        headers={"If-Match": stale_etag, "Content-Type": "text/plain"},
    )

    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "stale_file"
    assert detail["content"] == "edited in VS Code"
    assert target.read_bytes() == b"edited in VS Code"


async def test__put_file__without_if_match__still_writes_unconditionally(test_app: AsyncClient, tmp_path: Path) -> None:
    # Агент и внутренние операции буфера не держат — им условная запись не нужна.
    project_id, target = await _project_with_file(test_app, tmp_path, b"hello")
    target.write_bytes(b"edited in VS Code")

    resp = await test_app.put(
        f"/api/v1/projects/{project_id}/files/notes.tex",
        content=b"mine",
        headers={"Content-Type": "text/plain"},
    )

    assert resp.status_code == 204, resp.text
    assert target.read_bytes() == b"mine"
