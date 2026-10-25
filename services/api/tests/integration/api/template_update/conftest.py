from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.template_pack import build_update_pack, project_payload


@pytest_asyncio.fixture
async def update_app(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    """Приложение с синтетическим паком `upd-pack` (версии 2026.1 и 2026.1.1)."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    packs_dir = tmp_path / "packs"
    build_update_pack(packs_dir)
    container = create_test_container(data_dir, packs_dir=packs_dir)
    app = create_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await container.close()


async def create_project(client: AsyncClient, folder: Path, **kwargs: Any) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_payload(folder, **kwargs))
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def project(update_app: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    return await create_project(update_app, tmp_path / "proj")
