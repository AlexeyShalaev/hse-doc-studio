from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID, edit_tracked_file


async def test__api__create_vcs_snapshot__clean_tree__returns_null(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.post(f"/api/v1/projects/{project['id']}/vcs/snapshots", json={"message": "nothing changed"})

    assert resp.status_code == 200, resp.text
    assert resp.json() is None


async def test__api__create_vcs_snapshot__after_real_edit__returns_commit_and_cleans_tree(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "snapshot me")

    resp = await test_app.post(f"/api/v1/projects/{project_id}/vcs/snapshots", json={"message": "my milestone"})

    assert resp.status_code == 200, resp.text
    commit = resp.json()
    assert commit is not None
    assert commit["message"] == "my milestone"
    assert commit["kind"] == "manual"
    assert commit["id"]
    assert commit["short_id"]

    status_resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/status")
    assert status_resp.json()["dirty"] is False


async def test__api__create_vcs_snapshot__shows_up_in_history(test_app: AsyncClient, project: dict[str, Any]) -> None:
    project_id = project["id"]
    edit_tracked_file(project, "history entry")

    snap_resp = await test_app.post(f"/api/v1/projects/{project_id}/vcs/snapshots", json={"message": "for history"})
    commit_id = snap_resp.json()["id"]

    history_resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/history")

    assert history_resp.status_code == 200, history_resp.text
    history = history_resp.json()
    assert history[0]["id"] == commit_id
    assert history[0]["message"] == "for history"
    # The project-creation root snapshot ("init") is still there, underneath.
    assert any(c["kind"] == "init" for c in history)


async def test__api__create_vcs_snapshot__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.post(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/snapshots", json={"message": "x"})

    assert resp.status_code == 404
