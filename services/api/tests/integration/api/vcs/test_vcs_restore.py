from __future__ import annotations

from pathlib import Path
from typing import Any

from httpx import AsyncClient

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID, TRACKED_FILE, edit_tracked_file


async def _snapshot(client: AsyncClient, project_id: str, message: str) -> dict[str, Any]:
    resp = await client.post(f"/api/v1/projects/{project_id}/vcs/snapshots", json={"message": message})
    assert resp.status_code == 200, resp.text
    commit = resp.json()
    assert commit is not None
    return commit


def _read_tracked_file(project: dict[str, Any]) -> str:
    return (Path(project["folder"]) / TRACKED_FILE).read_text(encoding="utf-8")


async def test__api__restore_vcs__snapshot_mode__reverts_file_and_records_a_new_commit(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "first change")
    first_commit = await _snapshot(test_app, project_id, "first change")
    edit_tracked_file(project, "second change")
    await _snapshot(test_app, project_id, "second change")
    assert "second change" in _read_tracked_file(project)

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/vcs/restore",
        json={"commit_id": first_commit["id"], "mode": "snapshot"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["restored_from"] == first_commit["id"]
    assert data["new_snapshot_id"]  # a new "restore" commit was made — undoable
    assert data["files_changed"] == 1
    # The file on disk really reverted: "second change" is gone.
    content = _read_tracked_file(project)
    assert "first change" in content
    assert "second change" not in content

    history_resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/history")
    assert history_resp.json()[0]["kind"] == "restore"


async def test__api__restore_vcs__hard_mode_without_confirm__is_refused(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "change")
    commit = await _snapshot(test_app, project_id, "change")

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/vcs/restore",
        json={"commit_id": commit["id"], "mode": "hard"},
    )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"]


async def test__api__restore_vcs__hard_mode_with_confirm__resets_working_tree(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "keep me")
    target_commit = await _snapshot(test_app, project_id, "keep me")
    edit_tracked_file(project, "throw me away")
    await _snapshot(test_app, project_id, "throw me away")

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/vcs/restore",
        json={"commit_id": target_commit["id"], "mode": "hard", "confirm": True},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["restored_from"] == target_commit["id"]
    # Hard reset rewrites the branch tip in place — no new commit is recorded.
    assert data["new_snapshot_id"] is None
    content = _read_tracked_file(project)
    assert "keep me" in content
    assert "throw me away" not in content


async def test__api__restore_vcs__unknown_mode__returns_400(test_app: AsyncClient, project: dict[str, Any]) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "change")
    commit = await _snapshot(test_app, project_id, "change")

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/vcs/restore",
        json={"commit_id": commit["id"], "mode": "not-a-real-mode"},
    )

    assert resp.status_code == 400
    assert "not-a-real-mode" in resp.json()["detail"]


async def test__api__restore_vcs__unknown_commit_id__returns_400(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.post(
        f"/api/v1/projects/{project['id']}/vcs/restore",
        json={"commit_id": "totally-not-a-commit", "mode": "snapshot"},
    )

    assert resp.status_code == 400


async def test__api__restore_vcs__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/restore",
        json={"commit_id": "irrelevant", "mode": "snapshot"},
    )

    assert resp.status_code == 404
