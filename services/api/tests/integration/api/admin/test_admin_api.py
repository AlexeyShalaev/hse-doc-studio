"""Каркас /api/admin: гард (401 и 404), ограничение host/IP, страницы, флаг capabilities.admin, local."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import Depends, FastAPI
from hse_doc_studio.api.admin_access import install_admin_access
from hse_doc_studio.api.auth_cookie import SESSION_COOKIE
from hse_doc_studio.api.config import Settings, settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.api.schemas.admin import Page, PageParams, page_params
from hse_doc_studio.core.identity.entities import Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.sessions import SessionService
from hse_doc_studio.use_cases.server_setup.state import KEY_SETUP_COMPLETED, SetupStateService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemorySessionRepository
from tests.fakes.identity import InMemoryIdentityStore, InMemoryInstanceSettingsRepository, InMemoryUserRepository

NOW = datetime.now(UTC)


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, users: InMemoryUserRepository, sessions: InMemorySessionRepository, conf: object) -> None:
        super().__init__()
        self._service = SessionService(sessions, users)
        self._settings = conf

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver([SessionCookieResolver(self._service), BearerActorResolver()])

    @provide
    def bootstrap(self) -> BootstrapUC:
        return BootstrapUC(SetupStateService(self._settings), AuthSettingsService(self._settings), self._service)  # type: ignore[arg-type]


type Make = Callable[[], AsyncClient]


class _Env:
    def __init__(self, users: InMemoryUserRepository, sessions: InMemorySessionRepository, make: Make) -> None:
        self.users = users
        self.sessions = sessions
        self.make = make

    async def login(self, uid: str, *, admin: bool) -> dict[str, str]:
        email = f"{uid}@example.org"
        await self.users.add(
            User(
                id=uid,
                email=email,
                email_normalized=normalize_email(email),
                name=uid,
                status=UserStatus.active,
                created_at=NOW,
                email_verified=True,
                is_instance_admin=admin,
            )
        )
        await self.sessions.add(
            Session(
                id_hash=hash_token(f"s-{uid}"),
                user_id=uid,
                csrf_token="csrf",
                created_at=NOW,
                last_seen_at=NOW,
                expires_at=NOW + timedelta(days=7),
                ip=None,
                user_agent="UA",
            )
        )
        return {"Cookie": f"{SESSION_COOKIE}=s-{uid}"}


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Env]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    users = InMemoryUserRepository(InMemoryIdentityStore())
    sessions = InMemorySessionRepository()
    conf = InMemoryInstanceSettingsRepository()
    await conf.set(KEY_SETUP_COMPLETED, True, source="test")
    clients: list[AsyncClient] = []
    containers = []

    def make() -> AsyncClient:
        app = FastAPI()
        app.include_router(api_router)
        admin = make_admin_router()

        @admin.get("/probe")
        async def probe() -> dict[str, bool]:
            return {"ok": True}

        @admin.get("/numbers", response_model=Page[int])
        async def numbers(params: PageParams = Depends(page_params)) -> Page[int]:  # noqa: B008
            return params.page(list(range(params.offset, params.offset + params.limit)), 500)

        app.include_router(admin)
        install_exception_handlers(app)
        install_admin_access(app, Settings(_env_file=None, admin=settings.admin))
        container = make_async_container(_Provider(users, sessions, conf), FastapiProvider())
        setup_dishka(container, app)
        containers.append(container)
        client = AsyncClient(transport=ASGITransport(app=app, client=("203.0.113.9", 5000)), base_url="http://test")
        clients.append(client)
        return client

    yield _Env(users, sessions, make)
    for client in clients:
        await client.aclose()
    for container in containers:
        await container.close()


async def test__admin_api__anonymous__401(env: _Env) -> None:
    response = await env.make().get("/api/admin/probe")

    assert response.status_code == 401
    assert response.json()["code"] == "auth_required"


async def test__admin_api__student__404_like_a_missing_route(env: _Env) -> None:
    headers = await env.login("student", admin=False)

    response = await env.make().get("/api/admin/probe", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


async def test__admin_api__admin__200(env: _Env) -> None:
    headers = await env.login("boss", admin=True)

    response = await env.make().get("/api/admin/probe", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test__admin_api__page_params__are_bounded_and_echoed(env: _Env) -> None:
    headers = await env.login("boss", admin=True)
    client = env.make()

    body = (await client.get("/api/admin/numbers?limit=3&offset=10", headers=headers)).json()

    assert body == {"items": [10, 11, 12], "total": 500, "limit": 3, "offset": 10}
    assert (await client.get("/api/admin/numbers", headers=headers)).json()["limit"] == 50
    for query in ("limit=0", "limit=201", "offset=-1"):
        assert (await client.get(f"/api/admin/numbers?{query}", headers=headers)).status_code == 422


async def test__admin_api__local_mode__404_even_for_admin(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = await env.login("boss", admin=True)
    monkeypatch.setattr(settings, "mode", StudioMode.local)

    response = await env.make().get("/api/admin/probe", headers=headers)

    assert response.status_code == 404


async def test__admin_access__disallowed_ip__404_for_everyone_including_admin(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.admin, "allowed_cidrs", ["10.0.0.0/8"])
    headers = await env.login("boss", admin=True)

    for path in ("/api/admin/probe", "/admin", "/admin/users", "/assets/admin-users-1a2b.js"):
        response = await env.make().get(path, headers=headers)
        assert response.status_code == 404, path
        assert response.json()["code"] == "not_found"
    anonymous = await env.make().get("/api/admin/probe")
    assert anonymous.status_code == 404


async def test__admin_access__allowed_ip_and_host__reaches_the_guard(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.admin, "allowed_cidrs", ["203.0.113.0/24"])
    monkeypatch.setattr(settings.admin, "allowed_hosts", ["admin.example.org"])
    headers = await env.login("boss", admin=True)
    client = env.make()

    allowed = await client.get("/api/admin/probe", headers={**headers, "Host": "admin.example.org"})
    wrong_host = await client.get("/api/admin/probe", headers={**headers, "Host": "studio.example.org"})
    anonymous = await client.get("/api/admin/probe", headers={"Host": "admin.example.org"})

    assert allowed.status_code == 200
    assert wrong_host.status_code == 404
    assert anonymous.status_code == 401


async def test__admin_access__forwarded_for_is_ignored_without_trusted_proxy(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.admin, "allowed_cidrs", ["10.0.0.0/8"])
    headers = await env.login("boss", admin=True)

    response = await env.make().get("/api/admin/probe", headers={**headers, "X-Forwarded-For": "10.1.1.1"})

    assert response.status_code == 404


async def test__admin_access__not_admin_paths__untouched(env: _Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings.admin, "allowed_cidrs", ["10.0.0.0/8"])

    response = await env.make().get("/api/v1/session/bootstrap")

    assert response.status_code == 200


async def test__bootstrap__capabilities_admin_follows_the_ip_restriction(
    env: _Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = await env.login("boss", admin=True)
    client = env.make()

    assert (await client.get("/api/v1/session/bootstrap", headers=headers)).json()["capabilities"]["admin"] is True

    monkeypatch.setattr(settings.admin, "allowed_cidrs", ["10.0.0.0/8"])

    assert (await client.get("/api/v1/session/bootstrap", headers=headers)).json()["capabilities"]["admin"] is False


def test__admin_config__bad_entry__refused_at_startup() -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        Settings(_env_file=None, admin={"allowed_cidrs": ["nonsense"]})


def test__admin_config__env_lists() -> None:
    cfg = Settings(
        _env_file=None, admin={"allowed_hosts": [" admin.example.org ", ""], "allowed_cidrs": ["10.0.0.0/8"]}
    )

    assert cfg.admin.allowed_hosts == ["admin.example.org"]
    assert cfg.admin.policy.restricted
