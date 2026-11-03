"""Экрана «Локальная версия» в локальной Студии нет: его отдаёт только сервер."""

from __future__ import annotations

from httpx import AsyncClient


async def test__local_studio_info__local_mode__not_found(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/local-studio")

    assert resp.status_code == 404
