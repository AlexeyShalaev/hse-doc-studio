from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def test__api__get_projects__returns_list(test_app: AsyncClient, tmp_path: Path) -> None:
    project_folder = tmp_path / "my-vkr-list"
    project_folder.mkdir()
    payload = project_api_payload(str(project_folder))
    create_resp = await test_app.post("/api/v1/projects", json=payload)
    assert create_resp.status_code == 201, create_resp.text

    response = await test_app.get("/api/v1/projects")

    assert response.status_code == 200, response.text
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
