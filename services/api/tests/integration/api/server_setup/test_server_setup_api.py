"""Мастер первого запуска сервера: ручки, шлюз 503 и запуск с админом из окружения."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
import structlog
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import APIRouter, Depends, FastAPI
from hse_doc_studio.api import route_scopes
from hse_doc_studio.api.auth_cookie import SESSION_COOKIE
from hse_doc_studio.api.config import Settings, settings
from hse_doc_studio.api.config.auth import AuthConfig
from hse_doc_studio.api.guards import install_exception_handlers, project_access_guard
from hse_doc_studio.api.observability.health import HealthRegistry
from hse_doc_studio.api.route_scopes import RouteScope
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.api.server_setup import prepare_server_setup
from hse_doc_studio.core.identity.auth_settings import AuthEnvOverrides
from hse_doc_studio.core.identity.entities import RegistrationMode, User, UserStatus
from hse_doc_studio.core.identity.normalize import normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver, IUserRepository
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.identity.sessions import SessionService
from hse_doc_studio.use_cases.server_setup.admin import CreateFirstAdminUC, EnsureBootstrapAdminUC
from hse_doc_studio.use_cases.server_setup.settings import ApplyInitialSettingsUC, CompleteSetupUC
from hse_doc_studio.use_cases.server_setup.state import GetSetupStatusUC, SetupStateService
from hse_doc_studio.use_cases.server_setup.token import SetupToken
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import (
    InMemoryAuditLog,
    InMemoryLoginAttemptRepository,
    InMemorySessionRepository,
    empty_bearer_resolver,
)
from tests.fakes.identity import (
    InMemoryCredentialRepository,
    InMemoryFirstAdminRepository,
    InMemoryIdentityStore,
    InMemoryInstanceSettingsRepository,
    InMemoryUserRepository,
)
from tests.unit.use_cases.identity.conftest import FakeHasher, FakeUow

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"
PASSWORD = "correct horse battery"
NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
TOKEN = "st_test_token_value"  # noqa: S105 — тестовый токен


class _NoOidc:
    async def list(self, *, only_enabled: bool = False) -> list[object]:  # noqa: ARG002
        return []


class _World:
    def __init__(self, env: AuthEnvOverrides | None = None, *, token_required: bool = True) -> None:
        store = InMemoryIdentityStore()
        self.users = InMemoryUserRepository(store)
        self.first_admin = InMemoryFirstAdminRepository(store)
        self.creds = InMemoryCredentialRepository(store)
        self.sessions = InMemorySessionRepository()
        self.audit = InMemoryAuditLog()
        self.settings = InMemoryInstanceSettingsRepository()
        self.state = SetupStateService(self.settings)
        self.token = SetupToken(required=token_required, value=TOKEN if token_required else None)
        self.env = env or AuthEnvOverrides()
        self.hasher = FakeHasher()
        self.session_service = SessionService(self.sessions, self.users)

    def login(self) -> LoginUC:
        return LoginUC(
            self.users, self.creds, self.sessions, InMemoryLoginAttemptRepository(), self.hasher, self.audit, FakeUow()
        )

    def auth_settings(self) -> AuthSettingsService:
        return AuthSettingsService(self.settings, self.env)


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, world: _World) -> None:
        super().__init__()
        self._w = world

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver([SessionCookieResolver(self._w.session_service), empty_bearer_resolver()])

    @provide
    def users(self) -> IUserRepository:
        return self._w.users

    @provide
    def state(self) -> SetupStateService:
        return self._w.state

    @provide
    def token(self) -> SetupToken:
        return self._w.token

    @provide
    def login(self) -> LoginUC:
        return self._w.login()

    @provide
    def bootstrap(self) -> BootstrapUC:
        return BootstrapUC(self._w.state, self._w.auth_settings(), self._w.session_service)

    @provide
    def status(self) -> GetSetupStatusUC:
        w = self._w
        return GetSetupStatusUC(w.state, w.settings, w.users, w.token, w.env)

    @provide
    def create_admin(self) -> CreateFirstAdminUC:
        w = self._w
        return CreateFirstAdminUC(w.first_admin, w.hasher, w.login(), w.token, w.state, w.audit)

    @provide
    def ensure_admin(self) -> EnsureBootstrapAdminUC:
        w = self._w
        return EnsureBootstrapAdminUC(w.users, w.first_admin, w.hasher, w.state, w.audit, w.env)

    @provide
    def apply_settings(self) -> ApplyInitialSettingsUC:
        w = self._w
        service = w.auth_settings()
        return ApplyInitialSettingsUC(service, UpdateAuthSettingsUC(service, w.settings, w.audit), _NoOidc(), w.state)

    @provide
    def auth_settings_service(self) -> AuthSettingsService:
        return self._w.auth_settings()

    @provide
    def complete(self) -> CompleteSetupUC:
        return CompleteSetupUC(self._w.state, self._w.audit)


def _probe_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(project_access_guard)])

    @router.get("/probe/me")
    async def me() -> dict[str, bool]:
        return {"ok": True}

    return router


def _build_app(world: _World, *, gate: bool) -> tuple[FastAPI, Any]:
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(_probe_router())
    install_exception_handlers(app)
    container = make_async_container(_Provider(world), FastapiProvider())
    setup_dishka(container, app)
    if gate:
        app.state.setup_gate = world.state
    return app, container


@asynccontextmanager
async def _client(world: _World, *, gate: bool = True) -> AsyncIterator[AsyncClient]:
    app, container = _build_app(world, gate=gate)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await container.close()


@pytest.fixture(autouse=True)
def server_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setitem(route_scopes.ROUTE_SCOPES, ("GET", "/probe/me"), RouteScope.authenticated)


@pytest_asyncio.fixture
async def world() -> _World:
    return _World()


def _admin_body(**override: Any) -> dict[str, Any]:
    body = json.loads((_FIXTURES / "ServerSetupAdminRequest" / "with_token.json").read_text(encoding="utf-8"))
    body.update({"setup_token": TOKEN, "password": PASSWORD, **override})
    return body


def _settings_body(**override: Any) -> dict[str, Any]:
    body = json.loads((_FIXTURES / "ServerSetupSettingsRequest" / "domains.json").read_text(encoding="utf-8"))
    body.update(override)
    return body


async def _add_member(world: _World, client: AsyncClient) -> dict[str, str]:
    """Обычный пользователь входит по паролю; возвращает его cookie."""
    email = "m@example.org"
    user = User(
        id="m1", email=email, email_normalized=normalize_email(email), name="M",
        status=UserStatus.active, created_at=NOW, email_verified=True,
    )  # fmt: skip
    await world.users.add(user)
    await world.creds.set_hash(user.id, world.hasher.hash(PASSWORD))
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Cookie": f"{SESSION_COOKIE}={login.cookies[SESSION_COOKIE]}"}


async def _setup_admin(client: AsyncClient) -> dict[str, str]:
    response = await client.post("/api/v1/server-setup/admin", json=_admin_body())
    assert response.status_code == 200, response.text
    return {"Cookie": f"{SESSION_COOKIE}={response.cookies[SESSION_COOKIE]}"}


async def test__status__fresh_install__matches_fixture(world: _World) -> None:
    async with _client(world) as client:
        response = await client.get("/api/v1/server-setup/status")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"state": "needs_admin", "token_required": True, "steps_done": []}


async def test__admin__wrong_token__403_and_nothing_created(world: _World) -> None:
    async with _client(world) as client:
        response = await client.post("/api/v1/server-setup/admin", json=_admin_body(setup_token="st_wrong"))

    assert response.status_code == 403
    assert response.json()["code"] == "setup_token_invalid"
    assert await world.users.count() == 0
    assert SESSION_COOKIE not in response.cookies


async def test__admin__created__signed_in_with_csrf_and_cookie_flags(world: _World) -> None:
    async with _client(world) as client:
        response = await client.post("/api/v1/server-setup/admin", json=_admin_body())
        status = (await client.get("/api/v1/server-setup/status")).json()

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["is_instance_admin"] is True
    assert body["csrf_token"]
    assert "httponly" in response.headers["set-cookie"].lower()
    assert status == {"state": "needs_admin", "token_required": False, "steps_done": ["admin"]}


async def test__admin__two_parallel_requests__exactly_one_wins(world: _World) -> None:
    async with _client(world) as client:
        responses = await asyncio.gather(
            client.post("/api/v1/server-setup/admin", json=_admin_body(email="a@example.org")),
            client.post("/api/v1/server-setup/admin", json=_admin_body(email="b@example.org")),
        )

    assert sorted(r.status_code for r in responses) == [200, 409]
    assert await world.users.count() == 1


async def test__admin__invalid_email_or_weak_password__rejected(world: _World) -> None:
    async with _client(world) as client:
        bad_email = await client.post("/api/v1/server-setup/admin", json=_admin_body(email="nope"))
        weak = await client.post("/api/v1/server-setup/admin", json=_admin_body(password="short"))

    assert bad_email.status_code == 422
    assert weak.status_code == 422
    assert weak.json()["code"] == "password_policy"
    assert await world.users.count() == 0


async def test__admin__password_never_reaches_logs_or_audit(world: _World, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    with structlog.testing.capture_logs() as events:
        async with _client(world) as client:
            response = await client.post("/api/v1/server-setup/admin", json=_admin_body())

    assert PASSWORD not in caplog.text
    assert PASSWORD not in json.dumps(events, default=str)
    assert PASSWORD not in response.text
    assert PASSWORD not in repr(await world.audit.list())


async def test__admin__existing_admin__409_setup_already_done(world: _World) -> None:
    async with _client(world) as client:
        await _setup_admin(client)
        response = await client.post("/api/v1/server-setup/admin", json=_admin_body(email="other@example.org"))

    assert response.status_code == 409
    assert response.json()["code"] == "setup_already_done"


async def test__settings__needs_an_admin_session(world: _World) -> None:
    async with _client(world) as client:
        anonymous = await client.post("/api/v1/server-setup/settings", json=_settings_body())
        await _setup_admin(client)
        client.cookies.clear()
        member = await _add_member(world, client)
        regular = await client.post("/api/v1/server-setup/settings", json=_settings_body(), headers=member)

    assert anonymous.status_code == 401
    assert regular.status_code == 403


async def test__settings_and_complete__full_flow_then_everything_is_404(world: _World) -> None:
    async with _client(world) as client:
        cookie = await _setup_admin(client)
        applied = await client.post("/api/v1/server-setup/settings", json=_settings_body(), headers=cookie)
        done = await client.post("/api/v1/server-setup/complete", headers=cookie)
        after = [
            await client.get("/api/v1/server-setup/status"),
            await client.get("/api/v1/server-setup/environment", headers={"X-Setup-Token": TOKEN}),
            await client.post("/api/v1/server-setup/admin", json=_admin_body()),
            await client.post("/api/v1/server-setup/settings", json=_settings_body(), headers=cookie),
            await client.post("/api/v1/server-setup/complete", headers=cookie),
        ]
        bootstrap = (await client.get("/api/v1/session/bootstrap")).json()

    assert applied.json() == {"state": "needs_admin", "token_required": False, "steps_done": ["admin", "settings"]}
    assert done.json() == {"state": "ready", "token_required": False, "steps_done": ["admin", "settings"]}
    assert [r.status_code for r in after] == [404] * 5
    assert bootstrap["setup_state"] == "ready"
    assert bootstrap["auth"]["registration_mode"] == "domains"


async def test__settings_view__needs_an_admin_session(world: _World) -> None:
    async with _client(world) as client:
        anonymous = await client.get("/api/v1/server-setup/settings")
        await _setup_admin(client)
        client.cookies.clear()
        member = await _add_member(world, client)
        regular = await client.get("/api/v1/server-setup/settings", headers=member)

    assert anonymous.status_code == 401
    assert regular.status_code == 403


async def test__settings_view__defaults_are_editable(world: _World) -> None:
    async with _client(world) as client:
        cookie = await _setup_admin(client)
        response = await client.get("/api/v1/server-setup/settings", headers=cookie)

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "registration_mode": "invite",
        "registration_domains": [],
        "require_approval": False,
        "password_enabled": True,
        "locked_by_env": [],
    }


async def test__settings_view__env_keys_are_reported_locked_with_their_values() -> None:
    env = AuthEnvOverrides(registration_mode=RegistrationMode.domains, registration_domains=("hse.ru",))
    world = _World(env, token_required=False)
    async with _client(world) as client:
        cookie = await _setup_admin(client)
        response = await client.get("/api/v1/server-setup/settings", headers=cookie)

    body = response.json()
    assert body["registration_mode"] == "domains"
    assert body["registration_domains"] == ["hse.ru"]
    assert body["locked_by_env"] == ["registration_mode", "registration_domains"]


async def test__settings__domains_mode_without_domains__422(world: _World) -> None:
    async with _client(world) as client:
        cookie = await _setup_admin(client)
        response = await client.post(
            "/api/v1/server-setup/settings", json=_settings_body(registration_domains=[]), headers=cookie
        )

    assert response.status_code == 422


async def test__gate__before_completion__others_get_503_setup_required(world: _World) -> None:
    async with _client(world) as client:
        anonymous = await client.get("/api/v1/probe/me")
        public = await client.get("/api/v1/session/bootstrap")
        cookie = await _setup_admin(client)
        admin = await client.get("/api/v1/probe/me", headers=cookie)

    assert anonymous.status_code == 503
    assert anonymous.json()["code"] == "setup_required"
    assert public.status_code == 200
    assert public.json()["setup_state"] == "needs_admin"
    assert admin.status_code == 200


async def test__gate__regular_user_is_blocked_until_completion_then_let_in(world: _World) -> None:
    async with _client(world) as client:
        cookie = await _setup_admin(client)
        client.cookies.clear()
        member = await _add_member(world, client)
        blocked = await client.get("/api/v1/probe/me", headers=member)
        await client.post("/api/v1/server-setup/complete", headers=cookie)
        allowed = await client.get("/api/v1/probe/me", headers=member)
        client.cookies.clear()
        anonymous = await client.get("/api/v1/probe/me")

    assert blocked.status_code == 503
    assert allowed.status_code == 200
    assert anonymous.status_code == 401


async def test__gate__not_installed__nothing_changes(world: _World) -> None:
    async with _client(world, gate=False) as client:
        response = await client.get("/api/v1/probe/me")

    assert response.status_code == 401


async def test__environment__token_opens_it_before_the_admin_exists(world: _World) -> None:
    registry = HealthRegistry()

    async def database() -> str | None:
        return None

    async def storage() -> str | None:
        return "ClientConnectorError"

    registry.register("database", database)
    registry.register("s3", storage)
    app, container = _build_app(world, gate=True)
    app.state.health_registry = registry
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        without = await client.get("/api/v1/server-setup/environment")
        with_token = await client.get("/api/v1/server-setup/environment", headers={"X-Setup-Token": TOKEN})
        cookie = await _setup_admin(client)
        client.cookies.clear()
        token_after = await client.get("/api/v1/server-setup/environment", headers={"X-Setup-Token": TOKEN})
        with_admin = await client.get("/api/v1/server-setup/environment", headers=cookie)
    await container.close()

    assert without.status_code == 403
    assert with_token.status_code == 200
    assert with_token.json() == {
        "checks": [
            {"id": "database", "status": "ok", "reason": None},
            {"id": "storage", "status": "fail", "reason": "ClientConnectorError"},
            {"id": "runner", "status": "not_configured", "reason": None},
        ]
    }
    assert token_after.status_code == 401
    assert with_admin.status_code == 200


async def test__local_mode__the_wizard_does_not_exist(monkeypatch: pytest.MonkeyPatch, world: _World) -> None:
    monkeypatch.setattr(settings, "mode", StudioMode.local)
    async with _client(world) as client:
        response = await client.get("/api/v1/server-setup/status")

    assert response.status_code == 404


def _startup_container(world: _World) -> Any:
    return make_async_container(_Provider(world), FastapiProvider())


def _cfg(**auth: Any) -> Settings:
    return Settings(mode=StudioMode.server, auth=AuthConfig(**auth))


async def test__startup__without_env_admin__prints_the_setup_token_once(world: _World) -> None:
    container = _startup_container(world)
    app = FastAPI()

    with structlog.testing.capture_logs() as events:
        await prepare_server_setup(app, container, _cfg())

    await container.close()
    assert [e["setup_token"] for e in events if "setup_token" in e] == [TOKEN]
    assert app.state.setup_gate is world.state


async def test__startup__env_admin__created_idempotently_and_password_is_not_logged(tmp_path: Path) -> None:
    password_file = tmp_path / "admin_password"
    password_file.write_text(f"{PASSWORD}\n", encoding="utf-8")
    world = _World(AuthEnvOverrides(registration_mode=RegistrationMode.invite))
    cfg = _cfg(admin_email="root@example.org", admin_password_file=password_file)
    container = _startup_container(world)

    with structlog.testing.capture_logs() as events:
        await prepare_server_setup(FastAPI(), container, cfg)
        first_hash = await world.creds.get_hash((await world.users.get_by_email("root@example.org")).id)  # type: ignore[union-attr]
        await prepare_server_setup(FastAPI(), container, cfg)

    await container.close()
    assert await world.users.count() == 1
    admin = await world.users.get_by_email("root@example.org")
    assert admin is not None
    assert admin.is_instance_admin
    assert await world.creds.get_hash(admin.id) == first_hash
    assert PASSWORD not in json.dumps(events, default=str)
    assert TOKEN not in json.dumps(events, default=str)
    assert world.token.required is False
    assert await world.state.is_completed()


async def test__startup__weak_env_password__fails_loudly_without_echoing_it() -> None:
    world = _World()
    container = _startup_container(world)

    with pytest.raises(RuntimeError) as error:
        await prepare_server_setup(FastAPI(), container, _cfg(admin_email="root@example.org", admin_password="123"))

    await container.close()
    assert "123" not in str(error.value)
    assert "password_policy" in str(error.value)


async def test__startup__existing_users__the_token_is_not_printed() -> None:
    world = _World()
    await _create_admin_direct(world)
    container = _startup_container(world)

    with structlog.testing.capture_logs() as events:
        await prepare_server_setup(FastAPI(), container, _cfg())

    await container.close()
    assert not [e for e in events if "setup_token" in e]
    assert world.token.required is False


async def _create_admin_direct(world: _World) -> None:
    await EnsureBootstrapAdminUC(
        world.users, world.first_admin, world.hasher, world.state, world.audit, world.env
    ).execute("root@example.org", PASSWORD)
