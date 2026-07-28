from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.factories import project_api_payload


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test__api__list_changelog__empty_initially(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/changelog")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__add_changelog_entry__returns_201_with_entry(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    body = {"kind": "manual_note", "summary": "Manual note added", "doc_id": None, "note": "Some detail"}
    resp = await test_app.post(f"/api/v1/projects/{project_id}/changelog", json=body)

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["summary"] == "Manual note added"
    assert data["kind"] == "manual_note"
    assert "id" in data
    assert "at" in data


async def test__api__add_changelog_entry__appears_in_list(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    body = {"kind": "manual_note", "summary": "Entry in list", "doc_id": None, "note": None}
    await test_app.post(f"/api/v1/projects/{project_id}/changelog", json=body)

    resp = await test_app.get(f"/api/v1/projects/{project_id}/changelog")
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["summary"] == "Entry in list"


async def test__api__add_changelog_entry__unknown_kind__returns_400(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    body = {"kind": "invalid_kind_xyz", "summary": "Test", "doc_id": None, "note": None}
    resp = await test_app.post(f"/api/v1/projects/{project_id}/changelog", json=body)

    assert resp.status_code == 400


@pytest.mark.parametrize(
    ("method", "body"),
    [
        ("GET", None),
        ("POST", {"kind": "manual_note", "summary": "Test", "doc_id": None, "note": None}),
    ],
    ids=["list", "add_entry"],
)
async def test__api__changelog_endpoints__nonexistent_project__returns_404(
    test_app: AsyncClient, method: str, body: dict[str, str | None] | None
) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.request(method, f"/api/v1/projects/{fake_id}/changelog", json=body)

    assert resp.status_code == 404


async def test__api__list_changelog__limit_and_offset(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]

    for i in range(5):
        body = {"kind": "manual_note", "summary": f"Entry {i}", "doc_id": None, "note": None}
        await test_app.post(f"/api/v1/projects/{project_id}/changelog", json=body)

    resp = await test_app.get(f"/api/v1/projects/{project_id}/changelog?limit=2&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp2 = await test_app.get(f"/api/v1/projects/{project_id}/changelog?limit=2&offset=2")
    assert resp2.status_code == 200
    assert len(resp2.json()) == 2
