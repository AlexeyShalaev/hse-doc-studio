from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.config import settings as app_settings
from hse_doc_studio.api.schemas.git_sync import GitContentsResponse
from httpx import AsyncClient

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID, create_project

_LFS_POINTER = "version https://git-lfs.github.com/spec/v1\noid sha256:" + "ab" * 32 + "\nsize 5000000\n"


async def _snapshot(client: AsyncClient, project: dict[str, Any], message: str, **files: str | bytes) -> None:
    for name, data in files.items():
        target = Path(project["folder"]) / name.replace("__", "/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if isinstance(data, bytes) else data.encode())
    resp = await client.post(f"/api/v1/projects/{project['id']}/vcs/snapshots", json={"message": message})
    assert resp.status_code == 200, resp.text


async def _contents(client: AsyncClient, project: dict[str, Any]) -> GitContentsResponse:
    resp = await client.get(f"/api/v1/projects/{project['id']}/git/contents")
    assert resp.status_code == 200, resp.text
    return GitContentsResponse.model_validate(resp.json())


async def test__api__git_contents__fresh_project__counts_tracked_files_and_bot_commits(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await create_project(test_app, tmp_path / "proj")

    contents = await _contents(test_app, project)

    assert contents.files > 0
    assert contents.bytes > 0
    assert contents.commits == 1
    assert contents.bot_authored_commits == 1
    # Тестовый проект помечен NDA: расписка лежит в nda/.
    assert (contents.signatures, contents.nda_files, contents.lfs_pointers) == (0, 1, 0)
    assert contents.pdf_tracked is False
    assert contents.over_limit == []
    assert len(contents.largest) == 5
    sizes = [f.bytes for f in contents.largest]
    assert sizes == sorted(sizes, reverse=True)
    assert sum(sizes) <= contents.bytes


async def test__api__git_contents__sensitive_files__are_counted(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    await _snapshot(
        test_app,
        project,
        "sensitive",
        **{
            ".hse-studio__signatures__anna.png": b"\x89PNG one",
            ".hse-studio__signatures__boris.png": b"\x89PNG two",
            "nda__receipt.tex": "x",
            "ivanov__nda__receipt.tex": "x",
            "ivanov__nda.tex": "not a folder",
            "notes__nda": "a file, not a folder",
            "docs__pointer.bin": _LFS_POINTER,
            "docs__small.txt": "version 2\n",
        },
    )

    contents = await _contents(test_app, project)

    assert contents.signatures == 2
    assert contents.nda_files == 3  # расписка проекта и две новых в nda/
    assert contents.lfs_pointers == 1
    assert contents.commits == 2


async def test__api__git_contents__profile_commits__are_not_bot_authored(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    await test_app.put("/api/v1/profile", json={"name": "Алиса Иванова", "email": "alice@example.org"})
    await _snapshot(test_app, project, "mine", notes__a="x")

    contents = await _contents(test_app, project)

    assert (contents.commits, contents.bot_authored_commits) == (2, 1)


async def test__api__git_contents__big_blob_in_history__is_over_limit_even_after_deletion(
    test_app: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings.git, "large_file_warn_bytes", 600_000)
    project = await create_project(test_app, tmp_path / "proj")
    await _snapshot(test_app, project, "video", media__lecture_bin=b"\0" * 700_000, media__small_bin=b"\0" * 10)

    contents = await _contents(test_app, project)

    assert [(f.path, f.bytes, f.limit) for f in contents.over_limit] == [("media/lecture_bin", 700_000, 600_000)]
    assert contents.largest[0].path == "media/lecture_bin"
    assert contents.largest[0].bytes == 700_000

    (Path(project["folder"]) / "media" / "lecture_bin").unlink()
    await _snapshot(test_app, project, "removed")

    after = await _contents(test_app, project)

    assert [f.path for f in after.over_limit] == ["media/lecture_bin"]
    assert all(f.path != "media/lecture_bin" for f in after.largest)


async def test__api__git_contents__track_pdf_setting__is_reported(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    await test_app.patch(f"/api/v1/projects/{project['id']}/vcs/settings", json={"track_pdf": True})

    assert (await _contents(test_app, project)).pdf_tracked is True


async def test__api__git_contents__no_store__is_empty(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await create_project(test_app, tmp_path / "proj")
    shutil.rmtree(Path(project["folder"]) / ".hse-studio" / "git")

    contents = await _contents(test_app, project)

    assert (contents.files, contents.bytes, contents.commits, contents.largest) == (0, 0, 0, [])


async def test__api__git_contents__unknown_project__404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}/git/contents")

    assert resp.status_code == 404
