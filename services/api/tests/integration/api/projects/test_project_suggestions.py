from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def test__api__project_suggestions__no_projects_dir__returns_no_roots(
    test_app: AsyncClient,
) -> None:
    resp = await test_app.get("/api/v1/projects/suggestions")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["folder_roots"] == []
    assert data["authors"] == []


async def test__api__project_suggestions__fresh_install_with_projects_dir__suggests_it(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # На старте приложение создаёт `<data>/projects`; в тестовом приложении
    # startup-хуков нет, поэтому каталог заводим руками.
    projects_dir = tmp_path / "data" / "projects"
    projects_dir.mkdir()

    resp = await test_app.get("/api/v1/projects/suggestions")

    assert resp.status_code == 200, resp.text
    roots = resp.json()["folder_roots"]
    assert [Path(r["path"]) for r in roots] == [projects_dir]
    assert roots[0]["count"] == 0


async def test__api__project_suggestions__project_inside_default_dir__no_duplicate_root(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    projects_dir = tmp_path / "data" / "projects"
    projects_dir.mkdir()
    folder = projects_dir / "my-vkr"
    folder.mkdir()
    create_resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert create_resp.status_code == 201, create_resp.text

    resp = await test_app.get("/api/v1/projects/suggestions")

    assert resp.status_code == 200, resp.text
    roots = resp.json()["folder_roots"]
    assert [Path(r["path"]) for r in roots] == [projects_dir]
    # Реальный проект внутри — корень ранжирован по числу проектов, не как дефолт.
    assert roots[0]["count"] == 1
