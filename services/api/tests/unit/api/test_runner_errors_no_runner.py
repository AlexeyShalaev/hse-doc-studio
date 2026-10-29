"""Отсутствие раннера при постановке отвечает 503 с кодом протокола `no_runner`."""

from __future__ import annotations

from fastapi import FastAPI
from hse_doc_studio.api.runner_errors import install_runner_error_handlers
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from httpx import ASGITransport, AsyncClient


async def test__no_runner_available__is_503_with_protocol_code() -> None:
    app = FastAPI()
    install_runner_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise NoRunnerAvailableError(frozenset({"tex"}))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/boom")

    assert response.status_code == 503
    assert response.json()["code"] == "no_runner"
