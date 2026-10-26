from __future__ import annotations

from pathlib import Path

from hse_doc_studio.api.schemas.git_sync import CloneDefaultsResponse, SharedFolderResponse
from httpx import AsyncClient


async def test__api__shared_folder__plain_folder__not_detected(test_app: AsyncClient, tmp_path: Path) -> None:
    resp = await test_app.get("/api/v1/git/shared-folder", params={"folder": str(tmp_path / "course-paper")})

    assert resp.status_code == 200, resp.text
    body = SharedFolderResponse.model_validate(resp.json())
    assert (body.detected, body.provider, body.root, body.evidence) == (False, None, None, [])


async def test__api__shared_folder__yandex_disk_ancestor__detected(test_app: AsyncClient, tmp_path: Path) -> None:
    root = tmp_path / "Yandex.Disk.localized"
    folder = root / "Education" / "course-paper"

    resp = await test_app.get("/api/v1/git/shared-folder", params={"folder": str(folder)})

    body = SharedFolderResponse.model_validate(resp.json())
    assert (body.detected, body.provider, body.root) == (True, "yandex_disk", str(root))
    assert body.evidence == [str(root)]


async def test__api__shared_folder__syncthing_marker__detected(test_app: AsyncClient, tmp_path: Path) -> None:
    (tmp_path / "Sync" / ".stfolder").mkdir(parents=True)

    resp = await test_app.get("/api/v1/git/shared-folder", params={"folder": str(tmp_path / "Sync" / "paper")})

    body = SharedFolderResponse.model_validate(resp.json())
    assert (body.detected, body.provider) == (True, "syncthing")
    assert body.evidence == [f"{tmp_path / 'Sync'}/.stfolder"]


async def test__api__shared_folder__empty_or_nul_folder__rejected(test_app: AsyncClient) -> None:
    assert (await test_app.get("/api/v1/git/shared-folder", params={"folder": "a\0b"})).status_code == 400
    assert (await test_app.get("/api/v1/git/shared-folder", params={"folder": ""})).status_code == 422
    assert (await test_app.get("/api/v1/git/shared-folder")).status_code == 422


async def test__api__clone_defaults__name__is_folder_under_projects_dir(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/git/clone/defaults", params={"name": "Курсовая работа"})

    assert resp.status_code == 200, resp.text
    folder = Path(CloneDefaultsResponse.model_validate(resp.json()).folder)
    assert folder.name == "Курсовая-работа"
    assert folder.parent.name == "projects"
    assert not folder.exists()


async def test__api__clone_defaults__no_name__falls_back(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/git/clone/defaults")

    assert Path(resp.json()["folder"]).name == "project"
