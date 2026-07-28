from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def test__api__post_projects__creates_hse_studio_dir(test_app: AsyncClient, tmp_path: Path) -> None:
    project_folder = tmp_path / "my-vkr"
    project_folder.mkdir()
    payload = project_api_payload(str(project_folder))

    response = await test_app.post("/api/v1/projects", json=payload)

    assert response.status_code == 201, response.text
    studio_project_json = project_folder / ".hse-studio" / "project.json"
    assert studio_project_json.exists(), ".hse-studio/project.json should be created by CreateProjectUC"


async def test__api__post_projects__language_the_template_does_not_declare__rejected(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Project Proposal по регламенту ОП пишется только на английском (langs: [en]).
    payload = {**project_api_payload(str(tmp_path / "my-pp")), "template_id": "pp", "lang": "ru"}

    response = await test_app.post("/api/v1/projects", json=payload)

    assert response.status_code == 400, response.text


async def test__api__post_projects__rejected_create__leaves_no_folder_behind(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # Отказ не должен оставлять пустой каталог: он потом мешает повторной попытке.
    project_folder = tmp_path / "my-pp"
    payload = {**project_api_payload(str(project_folder)), "template_id": "pp", "lang": "ru"}

    await test_app.post("/api/v1/projects", json=payload)

    assert not project_folder.exists()
