from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID


async def test__api__get_vcs_settings__fresh_project__has_defaults(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    resp = await test_app.get(f"/api/v1/projects/{project['id']}/vcs/settings")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data == {
        "tracking_enabled": True,
        "auto_commit_on_compile": True,
        "track_pdf": False,
    }


async def test__api__get_vcs_settings__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/settings")

    assert resp.status_code == 404


async def test__api__update_vcs_settings__partial_patch__only_changes_given_field(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]

    resp = await test_app.patch(f"/api/v1/projects/{project_id}/vcs/settings", json={"track_pdf": True})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["track_pdf"] is True
    assert data["tracking_enabled"] is True
    assert data["auto_commit_on_compile"] is True


async def test__api__update_vcs_settings__persists_across_requests(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]
    await test_app.patch(
        f"/api/v1/projects/{project_id}/vcs/settings",
        json={"tracking_enabled": False, "auto_commit_on_compile": False},
    )

    resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/settings")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["tracking_enabled"] is False
    assert data["auto_commit_on_compile"] is False
    # Untouched by this PATCH — stays at its previous value.
    assert data["track_pdf"] is False


async def test__api__update_vcs_settings__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.patch(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/settings", json={"track_pdf": True})

    assert resp.status_code == 404
