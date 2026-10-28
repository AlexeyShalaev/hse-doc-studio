from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from hse_doc_studio.api.csrf import CSRF_HEADER, CsrfMiddleware
from httpx import ASGITransport, AsyncClient
from starlette.types import Scope

_SECRET = "s3cret"
_TOKEN = "csrf-token-1"
_ORIGIN = "https://studio.example.org"


async def _lookup(_scope: Scope, secret: str) -> str | None:
    return _TOKEN if secret == _SECRET else None


def _client() -> AsyncClient:
    app = FastAPI()

    @app.post("/api/v1/things")
    async def create() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/v1/things")
    async def read() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/api/runner/poll")
    async def runner() -> JSONResponse:
        return JSONResponse({"ok": True})

    app.add_middleware(CsrfMiddleware, allowed_origins=[_ORIGIN], lookup=_lookup)
    return AsyncClient(transport=ASGITransport(app=app), base_url="https://studio.example.org")


async def test__post_with_session_and_no_header__403_csrf_failed() -> None:
    async with _client() as client:
        response = await client.post("/api/v1/things", cookies={"hse_session": _SECRET})

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


async def test__post_with_wrong_token__403() -> None:
    async with _client() as client:
        response = await client.post("/api/v1/things", cookies={"hse_session": _SECRET}, headers={CSRF_HEADER: "no"})

    assert response.status_code == 403


async def test__post_with_valid_token__passes() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/things", cookies={"hse_session": _SECRET}, headers={CSRF_HEADER: _TOKEN, "Origin": _ORIGIN}
        )

    assert response.status_code == 200


async def test__get_with_session_needs_no_token() -> None:
    async with _client() as client:
        response = await client.get("/api/v1/things", cookies={"hse_session": _SECRET})

    assert response.status_code == 200


async def test__bearer_is_exempt() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/things", cookies={"hse_session": _SECRET}, headers={"Authorization": "Bearer pat"}
        )

    assert response.status_code == 200


async def test__signed_runner_route_is_exempt() -> None:
    async with _client() as client:
        response = await client.post("/api/runner/poll", cookies={"hse_session": _SECRET})

    assert response.status_code == 200


async def test__anonymous_post_passes_to_the_route() -> None:
    async with _client() as client:
        response = await client.post("/api/v1/things")

    assert response.status_code == 200


async def test__unknown_session_cookie_is_treated_as_anonymous() -> None:
    async with _client() as client:
        response = await client.post("/api/v1/things", cookies={"hse_session": "dead"})

    assert response.status_code == 200


@pytest.mark.parametrize("origin", ["https://evil.example", "null"])
async def test__foreign_origin__403_even_with_valid_token(origin: str) -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/things", cookies={"hse_session": _SECRET}, headers={CSRF_HEADER: _TOKEN, "Origin": origin}
        )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


async def test__foreign_origin_on_login_without_cookie__403() -> None:
    async with _client() as client:
        response = await client.post("/api/v1/things", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403


async def test__same_host_origin_is_allowed_without_public_url() -> None:
    app = FastAPI()

    @app.post("/x")
    async def x() -> dict[str, bool]:
        return {"ok": True}

    app.add_middleware(CsrfMiddleware, lookup=_lookup)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost:8000") as client:
        ok = await client.post("/x", headers={"Origin": "http://localhost:8000"})
        bad = await client.post("/x", headers={"Origin": "http://localhost:9999"})

    assert ok.status_code == 200
    assert bad.status_code == 403
