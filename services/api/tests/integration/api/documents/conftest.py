from __future__ import annotations

from pathlib import Path

import pytest_asyncio
from httpx import AsyncClient

from tests.factories import project_api_payload


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def project(test_app: AsyncClient, tmp_path: Path) -> dict:
    return await _create_project(test_app, tmp_path / "proj")
