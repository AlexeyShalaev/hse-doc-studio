from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hse_doc_studio.api.db_errors import install_db_error_handlers
from sqlalchemy.exc import IntegrityError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError


def _app(error: Exception) -> TestClient:
    app = FastAPI()
    install_db_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise error

    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "error",
    [
        OperationalError("SELECT 1", {}, ConnectionRefusedError("refused")),
        InterfaceError("SELECT 1", {}, RuntimeError("another operation is in progress")),
        PoolTimeoutError("QueuePool limit reached"),
    ],
    ids=["operational", "interface", "pool_timeout"],
)
def test__db_failure__503_db_unavailable_with_retry_after(error: Exception) -> None:
    response = _app(error).get("/boom")

    assert response.status_code == 503
    assert response.json()["code"] == "db_unavailable"
    assert response.headers["Retry-After"] == "5"


def test__constraint_violation__stays_500() -> None:
    response = _app(IntegrityError("INSERT", {}, ValueError("dup"))).get("/boom")

    assert response.status_code == 500


def test__foreign_connection_error__stays_500() -> None:
    response = _app(ConnectionResetError("smtp gone")).get("/boom")

    assert response.status_code == 500
