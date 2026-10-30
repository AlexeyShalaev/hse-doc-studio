"""Регистрация раннера и админка раннеров поверх настоящих маршрутов (серверный режим, фейковые репозитории)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.server_routers import include_server_routers
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.entities import ActorCredentials
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.jobs.wire import RUNNER_PROTOCOL_VERSION
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.runners import InMemoryRegistrationTokenRepository, InMemoryRunnerRepository

_ADMIN = Actor(kind="user", id="admin", is_instance_admin=True, source=ActorSource.session)
_USER = Actor.user("user")


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


class _HeldActorResolver:
    """Кто вошёл, задаёт тест; `None` значит аноним."""

    def __init__(self) -> None:
        self.actor: Actor | None = None

    async def resolve(self, _credentials: ActorCredentials) -> Actor | None:
        return self.actor


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self) -> None:
        super().__init__()
        self.resolver_ = _HeldActorResolver()
        self.registry = RunnerRegistry(
            InMemoryRunnerRepository(), InMemoryRegistrationTokenRepository(), InMemoryAuditLog(), _Uow()
        )

    @provide
    def registry_(self) -> RunnerRegistry:
        return self.registry

    @provide
    def resolver(self) -> IActorResolver:
        return self.resolver_


class _Env:
    def __init__(self, client: AsyncClient, resolver: _HeldActorResolver) -> None:
        self.client = client
        self.resolver = resolver


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    app = FastAPI()
    include_server_routers(app)
    install_exception_handlers(app)
    provider = _Provider()
    container = make_async_container(provider, FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        result = _Env(client, provider.resolver_)
        yield result
    await container.close()


def _body(**kwargs: object) -> dict[str, object]:
    return {
        "name": "r1",
        "protocol": RUNNER_PROTOCOL_VERSION,
        "version": "0.3.0",
        "tags": ["office"],
        "concurrency": 1,
        "resource_class": "standard",
        **kwargs,
    }


async def _admin_token(env: _Env) -> str:
    response = await env.client.post("/api/admin/runner-tokens", json={"label": "t"})
    assert response.status_code == 201
    return str(response.json()["secret"])


async def test__create_registration_token__returns_ready_start_command(env: _Env, as_actor) -> None:  # type: ignore[no-untyped-def]
    as_actor(_ADMIN)
    response = await env.client.post("/api/admin/runner-tokens", json={"label": "t"})
    assert response.status_code == 201
    body = response.json()
    assert body["command"].endswith("hse-doc-studio runner")
    assert f"HSE_RUNNER__TOKEN={body['secret']}" in body["command"]
    assert "HSE_RUNNER__API_URL=http" in body["command"]
    listed = await env.client.get("/api/admin/runner-tokens")
    assert body["secret"] not in listed.text


@pytest.fixture
def as_actor(env: _Env):  # type: ignore[no-untyped-def]
    def _set(actor: Actor | None) -> None:
        env.resolver.actor = actor

    return _set


async def test__register__with_admin_issued_token__returns_runner_token_once(env: _Env, as_actor) -> None:  # type: ignore[no-untyped-def]
    as_actor(_ADMIN)
    secret = await _admin_token(env)
    as_actor(None)

    response = await env.client.post(
        "/api/runner/v1/register", json=_body(), headers={"Authorization": f"Bearer {secret}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["runner_token"].startswith("hsrn_")
    assert (data["lease_s"], data["heartbeat_s"], data["max_poll_wait_s"]) == (45, 10, 25)
    again = await env.client.post(
        "/api/runner/v1/register", json=_body(), headers={"Authorization": f"Bearer {secret}"}
    )
    assert again.status_code == 401
    assert again.json()["code"] == "runner_unauthorized"


async def test__register__without_or_with_bad_token__401(env: _Env) -> None:
    for headers in ({}, {"Authorization": "Bearer hsrt_nope"}, {"Authorization": "Basic abc"}):
        response = await env.client.post("/api/runner/v1/register", json=_body(), headers=headers)
        assert response.status_code == 401
        assert response.json()["code"] == "runner_unauthorized"


async def test__register__old_protocol__409(env: _Env, as_actor) -> None:  # type: ignore[no-untyped-def]
    as_actor(_ADMIN)
    secret = await _admin_token(env)

    response = await env.client.post(
        "/api/runner/v1/register",
        json=_body(protocol=RUNNER_PROTOCOL_VERSION + 1),
        headers={"Authorization": f"Bearer {secret}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "runner_protocol_unsupported"


async def test__admin_routes__anonymous_401_non_admin_404(env: _Env, as_actor) -> None:  # type: ignore[no-untyped-def]
    routes = [
        ("GET", "/api/admin/runners"),
        ("GET", "/api/admin/runner-tokens"),
        ("POST", "/api/admin/runner-tokens"),
        ("DELETE", "/api/admin/runners/x"),
    ]
    as_actor(None)
    for method, path in routes:
        assert (await env.client.request(method, path, json={} if method == "POST" else None)).status_code == 401
    as_actor(_USER)
    for method, path in routes:
        assert (await env.client.request(method, path, json={} if method == "POST" else None)).status_code == 404


async def test__admin_flow__list_rotate_pause_revoke(env: _Env, as_actor) -> None:  # type: ignore[no-untyped-def]
    as_actor(_ADMIN)
    secret = await _admin_token(env)
    registered = (
        await env.client.post("/api/runner/v1/register", json=_body(), headers={"Authorization": f"Bearer {secret}"})
    ).json()
    runner_id = registered["runner_id"]

    listed = (await env.client.get("/api/admin/runners")).json()
    assert [r["id"] for r in listed] == [runner_id]
    assert "token" not in str(listed)
    assert registered["runner_token"] not in str(listed)
    tokens = (await env.client.get("/api/admin/runner-tokens")).json()
    assert tokens[0]["uses"] == 1
    assert secret not in str(tokens)

    assert (await env.client.patch(f"/api/admin/runners/{runner_id}", json={"paused": True})).status_code == 204
    assert (await env.client.get("/api/admin/runners")).json()[0]["paused"] is True
    rotated = await env.client.post(f"/api/admin/runners/{runner_id}/rotate-token")
    assert rotated.status_code == 200
    assert rotated.json()["runner_token"] != registered["runner_token"]
    assert (await env.client.delete(f"/api/admin/runners/{runner_id}")).status_code == 204
    assert (await env.client.get("/api/admin/runners")).json()[0]["revoked"] is True
    assert (await env.client.delete("/api/admin/runners/missing")).status_code == 404
    assert (await env.client.post("/api/admin/runners/missing/rotate-token")).status_code == 404


async def test__tokens__never_in_logs(env: _Env, as_actor, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    as_actor(_ADMIN)
    secret = await _admin_token(env)
    registered = (
        await env.client.post("/api/runner/v1/register", json=_body(), headers={"Authorization": f"Bearer {secret}"})
    ).json()

    assert secret not in caplog.text
    assert registered["runner_token"] not in caplog.text


async def test__local_mode__routes_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.local)
    app = FastAPI()
    include_server_routers(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/admin/runners")).status_code == 404
        assert (await client.post("/api/runner/v1/register", json=_body())).status_code == 404
