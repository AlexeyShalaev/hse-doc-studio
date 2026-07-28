from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID, edit_tracked_file


async def test__api__get_vcs_status__fresh_project__is_initialized_and_clean(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.get(f"/api/v1/projects/{project['id']}/vcs/status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["available"] is True
    assert data["initialized"] is True
    assert data["current_branch"] == "master"
    assert data["head"]
    assert data["dirty"] is False
    assert data["modified"] == 0
    assert data["untracked"] == 0
    assert data["last_snapshot_at"] is not None
    assert data["tracking_enabled"] is True


async def test__api__get_vcs_status__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/status")

    assert resp.status_code == 404


async def test__api__get_vcs_status__after_real_file_edit__is_dirty(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    edit_tracked_file(project, "a real edit")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/vcs/status")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["dirty"] is True
    assert data["modified"] == 1
    assert data["untracked"] == 0


async def test__api__init_vcs__already_initialized_project__is_idempotent(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.post(f"/api/v1/projects/{project['id']}/vcs/init")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["initialized"] is True
    assert data["available"] is True
    # Calling init again on an already-tracked project must not perturb the tree.
    assert data["dirty"] is False


async def test__api__init_vcs__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.post(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/init")

    assert resp.status_code == 404
