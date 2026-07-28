from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def test__connect__nonexistent_folder__404(test_app: AsyncClient, tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"

    resp = await test_app.post("/api/v1/projects/connect", json={"folder": str(missing)})

    assert resp.status_code == 404, resp.text


async def test__connect__path_is_file__400(test_app: AsyncClient, tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-folder.txt"
    file_path.write_text("hi", encoding="utf-8")

    resp = await test_app.post("/api/v1/projects/connect", json={"folder": str(file_path)})

    assert resp.status_code == 400, resp.text


async def test__connect__folder_without_hse_studio__400(test_app: AsyncClient, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    resp = await test_app.post("/api/v1/projects/connect", json={"folder": str(empty)})

    assert resp.status_code == 400, resp.text
    assert ".hse-studio" in resp.json()["detail"]


async def test__connect__reconnects_previously_unregistered_project(test_app: AsyncClient, tmp_path: Path) -> None:
    # Create then unregister, leaving .hse-studio/ on disk.
    project_folder = tmp_path / "existing-vkr"
    project_folder.mkdir()
    create_resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(project_folder)))
    assert create_resp.status_code == 201, create_resp.text
    project_id = create_resp.json()["id"]
    del_resp = await test_app.delete(f"/api/v1/projects/{project_id}")
    assert del_resp.status_code == 204, del_resp.text

    connect_resp = await test_app.post("/api/v1/projects/connect", json={"folder": str(project_folder)})

    assert connect_resp.status_code == 201, connect_resp.text
    body = connect_resp.json()
    assert body["folder"] == str(project_folder.resolve())
    assert body["lock"]["pack_id"] == "hse-cs-se"
    assert body["lock"]["template_id"] == "vkr"


async def test__connect__already_registered_folder__idempotent_returns_same_project(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    """Re-connecting an already-known folder must return the same project, not 400.

    Mirrors IDE "open project" semantics — opening an open project just focuses it.
    """
    project_folder = tmp_path / "already-here"
    project_folder.mkdir()
    create_resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(project_folder)))
    assert create_resp.status_code == 201, create_resp.text
    original_id = create_resp.json()["id"]

    connect_resp = await test_app.post("/api/v1/projects/connect", json={"folder": str(project_folder)})

    assert connect_resp.status_code == 201, connect_resp.text
    assert connect_resp.json()["id"] == original_id
    # Index still has exactly one entry (register() is idempotent).
    list_resp = await test_app.get("/api/v1/projects")
    assert list_resp.status_code == 200, list_resp.text
    same_folder = [p for p in list_resp.json() if p["folder"] == str(project_folder.resolve())]
    assert len(same_folder) == 1
