"""Локальный режим: сборку ведёт сама Студия, раннеры не нужны и кнопки не гаснут."""

from __future__ import annotations

from pathlib import Path

from httpx import AsyncClient

from tests.factories import project_api_payload


async def _project_id(test_app: AsyncClient, tmp_path: Path) -> str:
    folder = tmp_path / "proj"
    folder.mkdir()
    resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test__api__build_availability__local_mode__not_restricted(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id = await _project_id(test_app, tmp_path)

    resp = await test_app.get(f"/api/v1/projects/{project_id}/build-availability")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"cloud": False, "any_runner": True, "tags": ["office", "tex"], "reasons": {}}
    assert resp.headers["cache-control"] == "no-store"


async def test__api__documents__carry_build_tags(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id = await _project_id(test_app, tmp_path)

    resp = await test_app.get(f"/api/v1/projects/{project_id}/documents")

    assert resp.status_code == 200, resp.text
    docs = resp.json()
    assert docs
    assert all(set(doc["build_tags"]) <= {"tex", "office"} for doc in docs)
    assert any(doc["build_tags"] == ["tex"] for doc in docs if doc["engine"] is not None)


async def test__api__general_build_availability__local_mode__not_restricted(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/build-availability")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"cloud": False, "any_runner": True, "tags": ["office", "tex"], "reasons": {}}
    assert resp.headers["cache-control"] == "no-store"
