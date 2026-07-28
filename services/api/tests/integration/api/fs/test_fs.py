from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def test__api__browse__lists_directories_and_files(test_app: AsyncClient, tmp_path: Path) -> None:
    (tmp_path / "subdir-a").mkdir()
    (tmp_path / "subdir-b").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")

    resp = await test_app.get("/api/v1/fs/browse", params={"path": str(tmp_path)})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["path"] == str(tmp_path.resolve())
    assert data["parent"] == str(tmp_path.resolve().parent)
    names = [(e["name"], e["is_dir"]) for e in data["entries"]]
    assert ("subdir-a", True) in names
    assert ("subdir-b", True) in names
    assert ("file.txt", False) in names
    # directories first
    assert all(e["is_dir"] for e in data["entries"][:2])


async def test__api__browse__no_path__returns_home(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/fs/browse")

    assert resp.status_code == 200, resp.text
    assert resp.json()["path"] == str(Path.home().resolve())


async def test__api__browse__not_yet_created_path__lands_on_nearest_existing_ancestor(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # The create wizard appends the future project folder name to a picked
    # parent before it exists on disk — browse() must land on that parent
    # instead of 404ing, per BrowseFilesystemUC's documented behavior.
    resp = await test_app.get(
        "/api/v1/fs/browse",
        params={"path": str(tmp_path / "not-created-yet" / "nested")},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["path"] == str(tmp_path.resolve())


async def test__api__browse__path_is_a_file__returns_400(test_app: AsyncClient, tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")

    resp = await test_app.get("/api/v1/fs/browse", params={"path": str(file_path)})

    assert resp.status_code == 400


async def test__api__browse__expands_tilde(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/fs/browse", params={"path": "~"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["path"] == str(Path.home().resolve())


async def test__api__browse__hidden_entries_flagged(test_app: AsyncClient, tmp_path: Path) -> None:
    (tmp_path / ".hidden-dir").mkdir()
    (tmp_path / "visible-dir").mkdir()

    resp = await test_app.get("/api/v1/fs/browse", params={"path": str(tmp_path)})

    assert resp.status_code == 200, resp.text
    entries = {e["name"]: e for e in resp.json()["entries"]}
    assert entries[".hidden-dir"]["is_hidden"] is True
    assert entries["visible-dir"]["is_hidden"] is False


# ---------------------------------------------------------------------------
# Inspect tests — GET /api/v1/fs/inspect
# ---------------------------------------------------------------------------


async def test__api__inspect__nonexistent_path(test_app: AsyncClient, tmp_path: Path) -> None:
    resp = await test_app.get(
        "/api/v1/fs/inspect",
        params={"path": str(tmp_path / "no-such-folder")},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["exists"] is False
    assert body["is_dir"] is False
    assert body["has_project"] is False
    assert body["project"] is None


async def test__api__inspect__path_is_file(test_app: AsyncClient, tmp_path: Path) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_text("x", encoding="utf-8")

    resp = await test_app.get("/api/v1/fs/inspect", params={"path": str(file_path)})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["exists"] is True
    assert body["is_dir"] is False
    assert body["has_project"] is False


async def test__api__inspect__empty_dir(test_app: AsyncClient, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()

    resp = await test_app.get("/api/v1/fs/inspect", params={"path": str(empty)})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["exists"] is True
    assert body["is_dir"] is True
    assert body["has_project"] is False
    assert body["project"] is None


async def test__api__inspect__project_dir_returns_metadata(test_app: AsyncClient, tmp_path: Path) -> None:
    project_folder = tmp_path / "inspect-vkr"
    project_folder.mkdir()
    create_resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(project_folder)))
    assert create_resp.status_code == 201, create_resp.text

    resp = await test_app.get("/api/v1/fs/inspect", params={"path": str(project_folder)})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["exists"] is True
    assert body["is_dir"] is True
    assert body["has_project"] is True
    assert body["project"] is not None
    assert body["project"]["pack_id"] == "hse-cs-se"
    assert body["project"]["template_id"] == "vkr"
    assert body["project"]["version"] == "2026.1"
    assert body["project"]["name"]


async def test__api__inspect__expands_tilde(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/fs/inspect", params={"path": "~"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["exists"] is True
    assert body["is_dir"] is True
