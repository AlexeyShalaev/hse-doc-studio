"""Резолвер актора в server-режиме: cookie, отозванная сессия и аноним на гарде /api/v1."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import APIRouter, Depends, FastAPI
from hse_doc_studio.api import route_scopes
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers, project_access_guard
from hse_doc_studio.api.route_scopes import RouteScope
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.identity.entities import Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.sessions import SessionService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemorySessionRepository
from tests.fakes.identity import InMemoryIdentityStore, InMemoryUserRepository

SECRET = "valid-cookie-secret"
NOW = datetime.now(UTC)


class _Fixture:
    def __init__(self) -> None:
        self.sessions = InMemorySessionRepository()
        self.users = InMemoryUserRepository(InMemoryIdentityStore())


class _ResolverProvider(Provider):
    scope = Scope.APP

    def __init__(self, fixture: _Fixture) -> None:
        super().__init__()
        self._fixture = fixture

    @provide
    def get_resolver(self) -> IActorResolver:
        service = SessionService(self._fixture.sessions, self._fixture.users)
        return ChainActorResolver([SessionCookieResolver(service), BearerActorResolver()])


@pytest_asyncio.fixture
async def server_app(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, _Fixture]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(route_scopes, "ROUTE_SCOPES", {("GET", "/whoami"): RouteScope.authenticated})
    fixture = _Fixture()
    email = "ann@example.org"
    await fixture.users.add(
        User(
            id="u1",
            email=email,
            email_normalized=normalize_email(email),
            name="Ann",
            status=UserStatus.active,
            created_at=NOW,
            email_verified=True,
        )  # fmt: skip
    )
    await fixture.sessions.add(
        Session(
            id_hash=hash_token(SECRET),
            user_id="u1",
            csrf_token="c",
            created_at=NOW,
            last_seen_at=NOW,
            expires_at=NOW + timedelta(days=7),
        )  # fmt: skip
    )
    router = APIRouter(dependencies=[Depends(project_access_guard)])

    @router.get("/api/v1/whoami")
    async def whoami() -> dict[str, str | None]:
        actor = current_actor()
        return {"id": actor.id if actor else None, "source": actor.source.value if actor and actor.source else None}

    app = FastAPI()
    app.include_router(router)
    install_exception_handlers(app)
    container = make_async_container(_ResolverProvider(fixture), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, fixture
    await container.close()


async def test_no_cookie_is_401_auth_required(server_app: tuple[AsyncClient, _Fixture]) -> None:
    client, _ = server_app

    response = await client.get("/api/v1/whoami")

    assert response.status_code == 401
    assert response.json()["code"] == "auth_required"


async def test_valid_cookie_puts_actor_into_context(server_app: tuple[AsyncClient, _Fixture]) -> None:
    client, _ = server_app

    response = await client.get("/api/v1/whoami", headers={"Cookie": f"hse_session={SECRET}"})

    assert response.status_code == 200
    assert response.json() == {"id": "u1", "source": "session"}


async def test_host_prefixed_cookie_is_accepted(server_app: tuple[AsyncClient, _Fixture]) -> None:
    client, _ = server_app

    response = await client.get("/api/v1/whoami", headers={"Cookie": f"__Host-hse_session={SECRET}"})

    assert response.status_code == 200


async def test_revoked_session_is_401(server_app: tuple[AsyncClient, _Fixture]) -> None:
    client, fixture = server_app
    await fixture.sessions.delete(hash_token(SECRET))

    response = await client.get("/api/v1/whoami", headers={"Cookie": f"hse_session={SECRET}"})

    assert response.status_code == 401


async def test_bearer_stub_does_not_authenticate(server_app: tuple[AsyncClient, _Fixture]) -> None:
    client, _ = server_app

    response = await client.get("/api/v1/whoami", headers={"Authorization": "Bearer pat"})

    assert response.status_code == 401


async def test_local_mode_does_not_touch_the_container(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.local)
    router = APIRouter(dependencies=[Depends(project_access_guard)])

    @router.get("/api/v1/whoami")
    async def whoami() -> dict[str, str | None]:
        actor = current_actor()
        return {"kind": actor.kind.value if actor else None}

    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/whoami")

    assert response.json() == {"kind": "local"}
