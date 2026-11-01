"""Ошибки разбора запроса: глубокий JSON не даёт 500, а введённые значения не попадают в ответ и журнал."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.mode import StudioMode
from httpx import ASGITransport, AsyncClient

SECRET = "SuperSecret-Pass-888"  # noqa: S105 — тестовое значение


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    app = FastAPI()
    app.include_router(api_router)
    install_exception_handlers(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _nested(depth: int) -> str:
    return f'{{"password":"{SECRET}","z":' + "[" * depth + "]" * depth + "}"


@pytest.mark.parametrize("depth", [100, 3000, 5000])
async def test__login__deeply_nested_body__is_422_without_input(client: AsyncClient, depth: int) -> None:
    response = await client.post(
        "/api/v1/auth/login", content=_nested(depth), headers={"content-type": "application/json"}
    )

    assert response.status_code == 422
    assert SECRET not in response.text
    assert all(set(item) <= {"type", "loc", "msg"} for item in response.json()["detail"])


async def test__login__overlong_email__is_422(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": "a" * 600 + "@example.org", "password": "x"})

    assert response.status_code == 422
    assert "a" * 100 not in response.text
