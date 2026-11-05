"""Связь локальной Студии с облаком через API: имя устройства, сводка без входа на сервер, нет маршрутов на сервере."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest_asyncio
from hse_doc_studio.infra.di.providers.local_git_servers import LocalGitServersProvider
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container


@pytest_asyncio.fixture
async def test_app(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Локальная Студия со связью с облаком (в общей фикстуре серверов Студии нет)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    container = create_test_container(data_dir, extra_providers=[LocalGitServersProvider()])
    async with AsyncClient(transport=ASGITransport(app=create_test_app(container)), base_url="http://test") as client:
        yield client
    await container.close()


async def test__device__default_identity_is_stable_between_calls(test_app: AsyncClient) -> None:
    first = (await test_app.get("/api/v1/device")).json()
    second = (await test_app.get("/api/v1/device")).json()

    assert first["device_id"] == second["device_id"]
    assert len(first["device_id"]) == 32
    assert first["custom"] is False
    assert first["name"] == first["default_name"]


async def test__device__rename_and_reset(test_app: AsyncClient) -> None:
    renamed = await test_app.put("/api/v1/device", json={"name": "Ноутбук Алексея"})
    shown = (await test_app.get("/api/v1/device")).json()
    reset = await test_app.put("/api/v1/device", json={"name": ""})

    assert renamed.status_code == 200
    assert (shown["name"], shown["custom"]) == ("Ноутбук Алексея", True)
    assert reset.json()["custom"] is False
    assert reset.json()["device_id"] == shown["device_id"]


async def test__device__name_that_is_a_path_is_not_accepted_as_a_name(test_app: AsyncClient) -> None:
    response = await test_app.put("/api/v1/device", json={"name": "/Users/alex/work"})

    assert response.status_code == 200
    assert response.json()["custom"] is False


async def test__device__unknown_fields_are_rejected(test_app: AsyncClient) -> None:
    response = await test_app.put("/api/v1/device", json={"name": "x", "path": "/Users/alex"})

    assert response.status_code == 422


async def test__studio_link__without_a_server_login_shows_the_device_and_no_servers(test_app: AsyncClient) -> None:
    response = await test_app.get("/api/v1/git/studio-link")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["servers"] == []
    assert body["runner"]["paired"] is False
    assert body["endpoints"] == []
    assert body["project"] is None
    assert len(body["device"]["device_id"]) == 32


async def test__studio_link__rejects_a_malformed_project_id(test_app: AsyncClient) -> None:
    assert (await test_app.get("/api/v1/git/studio-link", params={"project": "not-a-uuid"})).status_code == 422


async def test__builds__unknown_project_is_not_found(test_app: AsyncClient) -> None:
    assert (await test_app.get(f"/api/v1/projects/{uuid4()}/git/builds")).status_code == 404
    assert (
        await test_app.post(f"/api/v1/projects/{uuid4()}/git/builds/fetch", json={"doc_id": "x"})
    ).status_code == 404
    assert (
        await test_app.post(f"/api/v1/projects/{uuid4()}/git/builds/cancel", json={"doc_id": None})
    ).status_code == 404
