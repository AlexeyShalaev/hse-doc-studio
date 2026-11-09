"""Локальная Студия: профиля подписанта нет, человек один и картинку держит в проекте (маршруты отвечают 404)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/account/signer-profile"),
        ("GET", "/api/v1/account/signer-profile/image"),
        ("DELETE", "/api/v1/account/signer-profile/image"),
        ("DELETE", "/api/v1/account/signer-profile/public-key"),
    ],
)
async def test__signer_profile__local_mode__404(test_app: AsyncClient, method: str, path: str) -> None:
    response = await test_app.request(method, path)

    assert response.status_code == 404
