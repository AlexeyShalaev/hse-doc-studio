from __future__ import annotations

from httpx import AsyncClient


async def test__api__list_documents__returns_list(test_app: AsyncClient, project: dict) -> None:
    project_id = project["id"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/documents")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 1


async def test__api__list_documents__items_have_expected_fields(test_app: AsyncClient, project: dict) -> None:
    project_id = project["id"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/documents")

    assert resp.status_code == 200
    item = resp.json()[0]
    assert "id" in item
    assert "status" in item


async def test__api__list_documents__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.get(f"/api/v1/projects/{fake_id}/documents")

    assert resp.status_code == 404


async def test__api__get_document__returns_detail(test_app: AsyncClient, project: dict) -> None:
    project_id = project["id"]
    docs_resp = await test_app.get(f"/api/v1/projects/{project_id}/documents")
    doc_id = docs_resp.json()[0]["id"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/documents/{doc_id}")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == doc_id
    assert "checks_override" in data


async def test__api__get_document__nonexistent_doc__returns_404(test_app: AsyncClient, project: dict) -> None:
    project_id = project["id"]

    resp = await test_app.get(f"/api/v1/projects/{project_id}/documents/no-such-doc")

    assert resp.status_code == 404


async def test__api__get_document__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.get(f"/api/v1/projects/{fake_id}/documents/vkr")

    assert resp.status_code == 404


async def test__api__update_document__checks_override_is_reflected(test_app: AsyncClient, project: dict) -> None:
    project_id = project["id"]
    docs_resp = await test_app.get(f"/api/v1/projects/{project_id}/documents")
    doc_id = docs_resp.json()[0]["id"]
    patch_body = {
        "checks_override": {
            "disabled_categories": ["formatting"],
            "disabled": ["r1"],
            "enabled": [],
            "severity_override": {},
        }
    }

    resp = await test_app.patch(f"/api/v1/projects/{project_id}/documents/{doc_id}", json=patch_body)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "formatting" in data["checks_override"]["disabled_categories"]
    assert "r1" in data["checks_override"]["disabled"]


async def test__api__update_document__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.patch(
        f"/api/v1/projects/{fake_id}/documents/vkr",
        json={"checks_override": None},
    )

    assert resp.status_code == 404
