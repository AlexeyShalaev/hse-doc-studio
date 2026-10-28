from __future__ import annotations

import pytest
from fastapi import Depends, FastAPI, Request
from hse_doc_studio.api.config import Settings, settings
from hse_doc_studio.api.identity_errors import install_identity_error_handlers
from hse_doc_studio.api.rate_limit import (
    EXPENSIVE_ROUTES,
    enforce_email,
    enforce_ip,
    install_rate_limiter,
    rate_limit_guard,
)
from hse_doc_studio.api.route_actions import ROUTE_ACTIONS
from hse_doc_studio.api.route_scopes import ROUTE_SCOPES
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.rate_limit import COMPILE, RULES, RateRule
from httpx import ASGITransport, AsyncClient

TIGHT = RateRule("auth_ip", limit=2, window_s=60)


def _app(*, limited: bool = True, scale: float = 1.0) -> FastAPI:
    app = FastAPI()
    install_identity_error_handlers(app)
    if limited:
        install_rate_limiter(app, Settings(_env_file=None, rate_limit={"scale": scale}))

    @app.post("/login")
    async def login(request: Request) -> dict[str, bool]:
        await enforce_ip(request, TIGHT)
        return {"ok": True}

    @app.post("/forgot")
    async def forgot(request: Request, email: str) -> dict[str, bool]:
        await enforce_email(request, email, TIGHT)
        return {"ok": True}

    async def as_user(request: Request) -> None:
        set_current_actor(Actor.user(request.headers["x-user"]))

    @app.post(
        "/api/v1/projects/{project_id}/documents/{doc_id}/compile",
        dependencies=[Depends(as_user), Depends(rate_limit_guard)],
    )
    async def compile_(project_id: str, doc_id: str) -> dict[str, bool]:
        return {"ok": True}

    return app


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test__login__over_limit__429_with_retry_after() -> None:
    async with _client(_app()) as client:
        assert (await client.post("/login")).status_code == 200
        assert (await client.post("/login")).status_code == 200
        response = await client.post("/login")
    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert 1 <= int(response.headers["retry-after"]) <= 60


async def test__no_limiter__nothing_is_limited() -> None:
    async with _client(_app(limited=False)) as client:
        for _ in range(10):
            assert (await client.post("/login")).status_code == 200


async def test__scale__changes_limits() -> None:
    async with _client(_app(scale=2)) as client:
        codes = [(await client.post("/login")).status_code for _ in range(5)]
    assert codes == [200, 200, 200, 200, 429]


async def test__forgot__email_key_is_normalized_and_isolated() -> None:
    async with _client(_app()) as client:
        for address in ("Ann@Example.org", "ann@example.org"):
            assert (await client.post("/forgot", params={"email": address})).status_code == 200
        assert (await client.post("/forgot", params={"email": " ANN@example.org"})).status_code == 429
        assert (await client.post("/forgot", params={"email": "bob@example.org"})).status_code == 200


@pytest.mark.parametrize(
    ("proxies", "forwarded", "expected_second"),
    [
        ([], "9.9.9.1", 429),  # заголовок от недоверенного пира игнорируется: адрес клиента один и тот же
        (["127.0.0.1"], "9.9.9.1", 200),  # от доверенного прокси клиентом считается адрес из заголовка
    ],
)
async def test__xff__trusted_only_from_configured_proxy(
    monkeypatch: pytest.MonkeyPatch, proxies: list[str], forwarded: str, expected_second: int
) -> None:
    monkeypatch.setattr(settings.auth, "trusted_proxies", proxies)
    async with _client(_app()) as client:
        for _ in range(2):
            await client.post("/login", headers={"x-forwarded-for": "9.9.9.9"})
        third = await client.post("/login", headers={"x-forwarded-for": forwarded})
    assert third.status_code == expected_second


async def test__guard__expensive_route__limited_per_user() -> None:
    path = "/api/v1/projects/p/documents/d/compile"
    async with _client(_app()) as client:
        for _ in range(COMPILE.limit):
            assert (await client.post(path, headers={"x-user": "u1"})).status_code == 200
        assert (await client.post(path, headers={"x-user": "u1"})).status_code == 429
        assert (await client.post(path, headers={"x-user": "u2"})).status_code == 200


def test__expensive_routes__are_real_project_or_user_routes() -> None:
    for key in EXPENSIVE_ROUTES:
        assert key in ROUTE_ACTIONS or key in ROUTE_SCOPES, key
    assert {rule.name for rule in EXPENSIVE_ROUTES.values()} <= set(RULES)
