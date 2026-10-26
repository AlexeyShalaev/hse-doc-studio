from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest_asyncio
from httpx import AsyncClient

from tests.factories import project_api_payload

FAKE_PROJECT_ID = "00000000-0000-0000-0000-000000000000"


@pytest_asyncio.fixture
async def project(test_app: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    folder = tmp_path / "proj"
    folder.mkdir()
    resp = await test_app.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()
