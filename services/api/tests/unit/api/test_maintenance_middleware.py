"""Режим обслуживания: 503 на /api, открыты /health и статус, статика, ручки восстановления вне записи."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from fastapi import FastAPI
from hse_doc_studio.api.maintenance import MaintenanceMiddleware
from httpx import ASGITransport, AsyncClient


class _Controller:
    def __init__(self) -> None:
        self.active = True
        self.writing = False

    def status(self) -> dict[str, object]:
        return {"active": self.active, "phase": "applying" if self.writing else "failed"}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[tuple[AsyncClient, _Controller]]:
    app = FastAPI()
    controller = _Controller()
    app.state.maintenance = controller
    for path in ("/api/v1/projects", "/api/admin/backups/restore", "/health", "/health/ready", "/admin/x"):
        app.add_api_route(path, lambda: {"ok": True}, methods=["GET"])
    app.add_middleware(MaintenanceMiddleware)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
        yield http, controller


async def test__active__api_gets_503_with_code(client: tuple[AsyncClient, _Controller]) -> None:
    http, _ = client
    r = await http.get("/api/v1/projects")
    assert r.status_code == 503
    assert r.json()["code"] == "maintenance"
    assert r.headers["retry-after"]
    assert (await http.get("/health/ready")).status_code == 503


async def test__active__health_status_static_and_restore_are_open(client: tuple[AsyncClient, _Controller]) -> None:
    http, controller = client
    assert (await http.get("/health")).status_code == 200
    assert (await http.get("/admin/x")).status_code == 200
    assert (await http.get("/api/maintenance")).json() == {"active": True, "phase": "failed"}
    assert (await http.get("/api/admin/backups/restore")).status_code == 200
    controller.writing = True
    assert (await http.get("/api/admin/backups/restore")).status_code == 503
    assert (await http.get("/api/maintenance")).status_code == 200


async def test__inactive__everything_passes(client: tuple[AsyncClient, _Controller]) -> None:
    http, controller = client
    controller.active = False
    assert (await http.get("/api/v1/projects")).status_code == 200
