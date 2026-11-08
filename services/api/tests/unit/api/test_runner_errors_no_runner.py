"""Отсутствие раннера при постановке отвечает 409 с кодом из каталога сервера и тегами без исполнителя."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from hse_doc_studio.api.runner_errors import install_runner_error_handlers
from hse_doc_studio.core.jobs.errors import NoRunnerAvailableError
from hse_doc_studio.core.jobs.runner_fit import PoolState, RunnerFit
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


async def test__no_runner_available__with_fit__reason_and_detail_name_it() -> None:
    app = FastAPI()
    install_runner_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        fit = RunnerFit(tags=frozenset({"office"}), shared=PoolState.absent, personal=PoolState.paused)
        raise NoRunnerAvailableError(frozenset({"office"}), any_runner=True, fit=fit)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/boom", headers={"Accept-Language": "ru"})

    body = response.json()
    assert (body["code"], body["reason"]) == ("no_runner_for_tags", "personal_paused")
    assert "личный раннер владельца на паузе" in body["detail"]


async def test__no_runner_available__without_fit__reason_is_null() -> None:
    app = FastAPI()
    install_runner_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise NoRunnerAvailableError(frozenset({"tex"}))

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as client:
        response = await client.get("/boom")

    assert response.json()["reason"] is None
