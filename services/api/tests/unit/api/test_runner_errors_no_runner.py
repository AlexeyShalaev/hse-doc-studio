"""Отсутствие раннера при постановке отвечает 409 с кодом из каталога сервера и тегами без исполнителя."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from hse_doc_studio.api.runner_errors import install_runner_error_handlers
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from httpx import ASGITransport, AsyncClient


@pytest.mark.parametrize(
    ("any_runner", "code"),
    [(False, "no_runners"), (True, "no_runner_for_tags")],
)
async def test__no_runner_available__is_409_with_code_and_tags(any_runner: bool, code: str) -> None:
    app = FastAPI()
    install_runner_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise NoRunnerAvailableError(frozenset({"office"}), any_runner=any_runner)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/boom")

    assert response.status_code == 409
    assert response.json()["code"] == code
    assert response.json()["tags"] == ["office"]
