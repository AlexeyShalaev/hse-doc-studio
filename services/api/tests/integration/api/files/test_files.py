from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.factories import project_api_payload

_FAKE_ID = "00000000-0000-0000-0000-000000000000"


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test__api__list_files__returns_list(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/files")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)


async def test__api__get_file__existing_file__returns_content(test_app: AsyncClient, tmp_path: Path) -> None:
    proj_folder = tmp_path / "proj"
    project = await _create_project(test_app, proj_folder)
    project_id = project["id"]
    (proj_folder / "hello.txt").write_text("hello world", encoding="utf-8")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/files/hello.txt")

    assert resp.status_code == 200, resp.text
    assert b"hello world" in resp.content


async def test__api__get_file__missing_file__returns_404(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/files/does-not-exist.txt")

    assert resp.status_code == 404


async def test__api__put_file__creates_file_and_get_returns_content(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    content = b"\\documentclass{article}\n\\begin{document}Hello\\end{document}"

    put_resp = await test_app.put(
        f"/api/v1/projects/{project_id}/files/main.tex",
        content=content,
    )
    assert put_resp.status_code == 204, put_resp.text

    get_resp = await test_app.get(f"/api/v1/projects/{project_id}/files/main.tex")
    assert get_resp.status_code == 200
    assert get_resp.content == content


async def test__api__put_file__updates_content_on_second_put(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    await test_app.put(f"/api/v1/projects/{project_id}/files/notes.txt", content=b"original")
    await test_app.put(f"/api/v1/projects/{project_id}/files/notes.txt", content=b"updated")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/files/notes.txt")

    assert resp.status_code == 200
    assert resp.content == b"updated"


async def test__api__list_files__contains_created_file(test_app: AsyncClient, tmp_path: Path) -> None:
    proj_folder = tmp_path / "proj"
    project = await _create_project(test_app, proj_folder)
    project_id = project["id"]
    (proj_folder / "notes.md").write_text("# Notes", encoding="utf-8")

    resp = await test_app.get(f"/api/v1/projects/{project_id}/files")

    assert resp.status_code == 200
    paths = [item["path"] for item in resp.json()]
    assert any("notes.md" in p for p in paths)


@pytest.mark.parametrize(
    ("method", "path_suffix", "content"),
    [
        pytest.param("GET", "/files", None, id="list"),
        pytest.param("GET", "/files/main.tex", None, id="get"),
        pytest.param("PUT", "/files/main.tex", b"content", id="put"),
    ],
)
async def test__api__files_endpoints__nonexistent_project__returns_404(
    test_app: AsyncClient, method: str, path_suffix: str, content: bytes | None
) -> None:
    resp = await test_app.request(method, f"/api/v1/projects/{_FAKE_ID}{path_suffix}", content=content)

    assert resp.status_code == 404
