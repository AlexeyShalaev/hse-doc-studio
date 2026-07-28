from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.integration.api.vcs.conftest import FAKE_PROJECT_ID


async def test__api__list_vcs_tags__fresh_project__is_empty(test_app: AsyncClient, project: dict[str, Any]) -> None:
    resp = await test_app.get(f"/api/v1/projects/{project['id']}/vcs/tags")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__list_vcs_tags__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/tags")

    assert resp.status_code == 404


async def test__api__create_vcs_tag__lightweight_tag__has_no_message(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]

    resp = await test_app.post(f"/api/v1/projects/{project_id}/vcs/tags", json={"name": "v1", "kind": "tag"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "v1"
    assert data["kind"] == "tag"
    assert data["message"] is None
    assert data["commit_id"]


async def test__api__create_vcs_tag__release_kind_with_message__round_trips(
    test_app: AsyncClient, project: dict[str, Any]
) -> None:
    project_id = project["id"]

    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/vcs/tags",
        json={"name": "v2", "kind": "release", "message": "первый релиз"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["kind"] == "release"
    assert data["message"] == "первый релиз"

    list_resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/tags")
    names = {t["name"]: t for t in list_resp.json()}
    assert names["v2"]["message"] == "первый релиз"


async def test__api__create_vcs_tag__unknown_kind__returns_400(test_app: AsyncClient, project: dict[str, Any]) -> None:
    resp = await test_app.post(
        f"/api/v1/projects/{project['id']}/vcs/tags", json={"name": "v3", "kind": "not-a-real-kind"}
    )

    assert resp.status_code == 400
    assert "not-a-real-kind" in resp.json()["detail"]


async def test__api__create_vcs_tag__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.post(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/tags", json={"name": "v1"})

    assert resp.status_code == 404


async def test__api__delete_vcs_tag__existing_tag__removes_it(test_app: AsyncClient, project: dict[str, Any]) -> None:
    project_id = project["id"]
    await test_app.post(f"/api/v1/projects/{project_id}/vcs/tags", json={"name": "to-delete"})

    resp = await test_app.delete(f"/api/v1/projects/{project_id}/vcs/tags", params={"name": "to-delete"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["deleted"] is True
    list_resp = await test_app.get(f"/api/v1/projects/{project_id}/vcs/tags")
    assert "to-delete" not in [t["name"] for t in list_resp.json()]


async def test__api__delete_vcs_tag__unknown_name__returns_400(test_app: AsyncClient, project: dict[str, Any]) -> None:
    resp = await test_app.delete(f"/api/v1/projects/{project['id']}/vcs/tags", params={"name": "ghost-tag"})

    assert resp.status_code == 400


async def test__api__delete_vcs_tag__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.delete(f"/api/v1/projects/{FAKE_PROJECT_ID}/vcs/tags", params={"name": "v1"})

    assert resp.status_code == 404
