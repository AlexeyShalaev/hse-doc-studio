from __future__ import annotations

import pytest
from fastapi import FastAPI
from hse_doc_studio.api.observability.client_ip import resolve_client_ip
from hse_doc_studio.api.observability.health import HealthRegistry, build_health_router, build_metrics_router
from hse_doc_studio.api.observability.metrics import MetricsMiddleware, MetricsRegistry
from hse_doc_studio.api.observability.request_id import REQUEST_ID_HEADER, RequestIdMiddleware, current_request_id
from httpx import ASGITransport, AsyncClient

_TRUSTED = ["10.0.0.0/8", "127.0.0.1"]


def test__client_ip__untrusted_peer__header_ignored() -> None:
    assert resolve_client_ip("203.0.113.5", "1.2.3.4", _TRUSTED) == "203.0.113.5"


def test__client_ip__trusted_peer__takes_rightmost_untrusted_hop() -> None:
    assert resolve_client_ip("10.0.0.2", "9.9.9.9, 198.51.100.7, 10.0.0.9", _TRUSTED) == "198.51.100.7"


def test__client_ip__garbage_in_chain__falls_back_to_peer() -> None:
    assert resolve_client_ip("10.0.0.2", "not-an-ip", _TRUSTED) == "10.0.0.2"


def test__client_ip__no_trusted_proxies__peer() -> None:
    assert resolve_client_ip("10.0.0.2", "1.1.1.1", []) == "10.0.0.2"


def _client(app: FastAPI) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _app(*, health_token: str | None = "hl", metrics_token: str | None = "mt") -> tuple[FastAPI, HealthRegistry]:
    health = HealthRegistry()
    metrics = MetricsRegistry()
    app = FastAPI()
    app.include_router(build_health_router(health, health_token=health_token))
    app.include_router(build_metrics_router(metrics, metrics_token=metrics_token))

    @app.get("/items/{item_id}")
    async def item(item_id: str) -> dict[str, str | None]:
        return {"id": item_id, "request_id": current_request_id()}

    app.add_middleware(MetricsMiddleware, registry=metrics)
    app.add_middleware(RequestIdMiddleware)
    return app, health


async def test__ready__anonymous__sees_only_status() -> None:
    app, health = _app()

    async def db() -> str | None:
        return "boom"

    health.register("database", db)
    async with _client(app) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "fail"}


async def test__ready__with_token__sees_details() -> None:
    app, health = _app()

    async def db() -> str | None:
        return None

    health.register("database", db)
    async with _client(app) as client:
        anon = await client.get("/health/ready")
        authed = await client.get("/health/ready", headers={"Authorization": "Bearer hl"})
        wrong = await client.get("/health/ready", headers={"Authorization": "Bearer nope"})

    assert anon.status_code == 200
    assert anon.json() == {"status": "ok"}
    assert authed.json()["checks"] == {"database": {"ok": True, "reason": None}}
    assert "checks" not in wrong.json()


async def test__ready__probe_raises__fails_without_leaking_text() -> None:
    app, health = _app()

    async def bad() -> str | None:
        raise RuntimeError("password=secret")

    health.register("database", bad)
    async with _client(app) as client:
        response = await client.get("/health/ready", headers={"Authorization": "Bearer hl"})

    assert response.status_code == 503
    assert "secret" not in response.text


async def test__ready__optional_probe_down__stays_ready_but_is_listed() -> None:
    app, health = _app()

    async def db() -> str | None:
        return None

    async def lt() -> str | None:
        return "no_healthy_replica"

    health.register("database", db)
    health.register("languagetool", lt, optional=True)
    async with _client(app) as client:
        response = await client.get("/health/ready", headers={"Authorization": "Bearer hl"})

    assert response.status_code == 200
    assert response.json()["checks"]["languagetool"] == {"ok": False, "reason": "no_healthy_replica"}


async def test__live__always_ok() -> None:
    app, _ = _app()
    async with _client(app) as client:
        assert (await client.get("/health/live")).json() == {"status": "ok"}


async def test__request_id__generated_and_echoed() -> None:
    app, _ = _app()
    async with _client(app) as client:
        generated = await client.get("/items/1")
        echoed = await client.get("/items/1", headers={REQUEST_ID_HEADER: "abc-12345678"})
        unsafe = await client.get("/items/1", headers={REQUEST_ID_HEADER: "bad id\t!"})

    assert generated.headers[REQUEST_ID_HEADER] == generated.json()["request_id"]
    assert echoed.headers[REQUEST_ID_HEADER] == "abc-12345678"
    assert unsafe.headers[REQUEST_ID_HEADER] != "bad id\t!"
    assert current_request_id() is None


@pytest.mark.parametrize("token", [None, "wrong"])
async def test__metrics__without_valid_token__404(token: str | None) -> None:
    app, _ = _app()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with _client(app) as client:
        assert (await client.get("/metrics", headers=headers)).status_code == 404


async def test__metrics__no_token_configured__404_even_with_header() -> None:
    app, _ = _app(metrics_token=None)
    async with _client(app) as client:
        assert (await client.get("/metrics", headers={"Authorization": "Bearer "})).status_code == 404


async def test__metrics__counts_by_route_template() -> None:
    app, _ = _app()
    async with _client(app) as client:
        await client.get("/items/a")
        await client.get("/items/b")
        await client.get("/nope")
        text = (await client.get("/metrics", headers={"Authorization": "Bearer mt"})).text

    assert 'hse_http_requests_total{method="GET",route="/items/{item_id}",status="2xx"} 2' in text
    assert 'route="unmatched",status="4xx"} 1' in text
    assert "hse_http_request_duration_seconds_count" in text


@pytest.mark.parametrize(("path", "expected"), [("/health/ready", 200), ("/metrics", 404)])
async def test__non_ascii_bearer__no_500(path: str, expected: int) -> None:
    app, _ = _app()
    async with _client(app) as client:
        response = await client.get(path, headers={"Authorization": b"Bearer caf\xe9"})
    assert response.status_code == expected
