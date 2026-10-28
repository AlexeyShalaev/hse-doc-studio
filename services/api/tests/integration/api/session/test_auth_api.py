"""Вход, выход, сессии аккаунта и bootstrap в серверном режиме против эталонов contracts/server."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.auth_cookie import SESSION_COOKIE
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.identity.auth_settings import KEY_PASSWORD_ENABLED, KEY_REGISTRATION_MODE
from hse_doc_studio.core.identity.entities import Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.login import LoginUC
from hse_doc_studio.use_cases.identity.sessions import (
    ListSessionsUC,
    LogoutUC,
    RevokeOtherSessionsUC,
    RevokeSessionUC,
    SessionService,
)
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemoryAuditLog, InMemoryLoginAttemptRepository, InMemorySessionRepository
from tests.fakes.identity import (
    InMemoryCredentialRepository,
    InMemoryIdentityStore,
    InMemoryInstanceSettingsRepository,
    InMemoryUserRepository,
)
from tests.fixtures.app import create_test_app, create_test_container

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"
PASSWORD = "correct horse battery"
NOW = datetime.now(UTC)


def _fixture(schema: str, name: str) -> Any:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


class _Hasher:
    def hash(self, password: str) -> str:
        return f"h:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"h:{password}"

    def needs_rehash(self, password_hash: str) -> bool:  # noqa: ARG002
        return False


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


class _World:
    def __init__(self) -> None:
        store = InMemoryIdentityStore()
        self.users = InMemoryUserRepository(store)
        self.creds = InMemoryCredentialRepository(store)
        self.sessions = InMemorySessionRepository()
        self.attempts = InMemoryLoginAttemptRepository()
        self.audit = InMemoryAuditLog()
        self.settings = InMemoryInstanceSettingsRepository()

    async def add_user(
        self, email: str = "anna.petrova@example.org", *, status: UserStatus = UserStatus.active, admin: bool = False
    ) -> User:
        user = User(
            id=f"u_{len(await self._ids())}",
            email=email,
            email_normalized=normalize_email(email),
            name="Анна Петрова",
            status=status,
            created_at=NOW,
            email_verified=True,
            is_instance_admin=admin,
            locale="ru",
        )
        await self.users.add(user)
        await self.creds.set_hash(user.id, _Hasher().hash(PASSWORD))
        return user

    async def _ids(self) -> list[str]:
        return [str(i) for i in range(await self.users.count())]

    async def add_session(self, user: User, secret: str, *, hours_ago: int = 0, ip: str | None = None) -> None:
        seen = NOW - timedelta(hours=hours_ago)
        await self.sessions.add(
            Session(
                id_hash=hash_token(secret),
                user_id=user.id,
                csrf_token=f"csrf-{secret}",
                created_at=seen,
                last_seen_at=seen,
                expires_at=NOW + timedelta(days=7),
                ip=ip,
                user_agent="UA",
            )
        )


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, world: _World) -> None:
        super().__init__()
        self._w = world
        self._service = SessionService(world.sessions, world.users)

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver([SessionCookieResolver(self._service), BearerActorResolver()])

    @provide
    def bootstrap(self) -> BootstrapUC:
        return BootstrapUC(self._w.users, AuthSettingsService(self._w.settings), self._service)

    @provide
    def login(self) -> LoginUC:
        w = self._w
        return LoginUC(w.users, w.creds, w.sessions, w.attempts, _Hasher(), w.audit, _Uow())

    @provide
    def logout(self) -> LogoutUC:
        return LogoutUC(self._w.sessions, self._w.audit)

    @provide
    def list_sessions(self) -> ListSessionsUC:
        return ListSessionsUC(self._w.sessions)

    @provide
    def revoke(self) -> RevokeSessionUC:
        return RevokeSessionUC(self._w.sessions, self._w.audit)

    @provide
    def revoke_others(self) -> RevokeOtherSessionsUC:
        return RevokeOtherSessionsUC(self._w.sessions, self._w.audit)


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, _World]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    world = _World()
    app = FastAPI()
    app.include_router(api_router)
    install_exception_handlers(app)
    container = make_async_container(_Provider(world), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, world
    await container.close()


def _cookie(secret: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={secret}"}


async def test_bootstrap_without_users_asks_for_first_admin(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    response = await client.get("/api/v1/session/bootstrap")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    expected = _fixture("Bootstrap", "server_needs_admin")
    assert body == {**expected, "version": body["version"]}


async def test_bootstrap_anonymous_matches_the_fixture(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()
    await world.settings.set(KEY_REGISTRATION_MODE, "open", source="test")

    body = (await client.get("/api/v1/session/bootstrap")).json()

    expected = _fixture("Bootstrap", "server_anonymous")
    # Без SMTP письма не уходят: фикстура описывает установку с почтой.
    expected["auth"]["smtp_enabled"] = False
    assert body == {**expected, "version": body["version"]}


async def test_bootstrap_sso_only_hides_password(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()
    await world.settings.set(KEY_PASSWORD_ENABLED, False, source="test")

    body = (await client.get("/api/v1/session/bootstrap")).json()

    assert body["auth"]["password_enabled"] is False
    assert body["auth"]["registration_mode"] == "invite"


async def test_bootstrap_with_session_returns_user_and_csrf(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user(admin=True)
    await world.add_session(user, "secret")

    body = (await client.get("/api/v1/session/bootstrap", headers=_cookie("secret"))).json()

    assert body["user"]["email"] == user.email
    assert body["user"]["avatar_initials"] == "АП"
    assert body["user"]["locale"] == "ru"
    assert body["csrf_token"] == "csrf-secret"
    assert body["capabilities"]["admin"] is True
    assert body["capabilities"]["fs_browse"] is False


async def test_bootstrap_with_dead_cookie_is_anonymous(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()

    body = (await client.get("/api/v1/session/bootstrap", headers=_cookie("gone"))).json()

    assert body["user"] is None
    assert body["csrf_token"] is None
    assert body["capabilities"]["admin"] is False


async def test_login_sets_cookie_and_matches_the_login_fixture_shape(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()

    response = await client.post("/api/v1/auth/login", json={"email": "Anna.Petrova@example.org", "password": PASSWORD})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(_fixture("LoginResponse", "member"))
    assert set(body["user"]) == set(_fixture("LoginResponse", "member")["user"])
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert response.headers["cache-control"] == "no-store"
    secret = response.cookies[SESSION_COOKIE]
    assert (await world.sessions.get(hash_token(secret))) is not None
    assert body["csrf_token"] == (await world.sessions.get(hash_token(secret))).csrf_token  # type: ignore[union-attr]


async def test_login_rotates_the_previous_session(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "old")

    response = await client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": PASSWORD}, headers=_cookie("old")
    )

    assert response.status_code == 200
    assert await world.sessions.get(hash_token("old")) is None


async def test_wrong_password_is_401_invalid_credentials(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()

    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "nope"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"
    assert set(response.json()) == set(
        _fixture("AuthErrorBody", next(p.stem for p in (_FIXTURES / "AuthErrorBody").glob("*.json")))
    )
    assert "set-cookie" not in response.headers


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (UserStatus.pending_verification, "email_not_verified"),
        (UserStatus.pending_approval, "pending_approval"),
        (UserStatus.disabled, "account_disabled"),
    ],
)
async def test_login_of_inactive_account_is_403_with_code(
    env: tuple[AsyncClient, _World], status: UserStatus, code: str
) -> None:
    client, world = env
    user = await world.add_user(status=status)

    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 403
    assert response.json()["code"] == code


async def test_login_is_refused_while_password_is_disabled(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.settings.set(KEY_PASSWORD_ENABLED, False, source="test")

    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 403
    assert response.json()["code"] == "sso_login_required"


async def test_repeated_failures_get_429_with_retry_after(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()

    last = None
    for _ in range(6):
        last = await client.post("/api/v1/auth/login", json={"email": user.email, "password": "nope"})

    assert last is not None
    assert last.status_code == 429
    assert last.json()["code"] == "rate_limited"
    assert int(last.headers["retry-after"]) >= 1


async def test_login_of_unknown_email_is_401(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    response = await client.post("/api/v1/auth/login", json={"email": "a@b.co", "password": "x"})

    assert response.status_code == 401


async def test_logout_deletes_session_and_clears_cookie(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "secret")

    response = await client.post("/api/v1/auth/logout", headers=_cookie("secret"))

    assert response.status_code == 204
    assert await world.sessions.get(hash_token("secret")) is None
    assert f"{SESSION_COOKIE}=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_logout_without_session_is_still_204(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    assert (await client.post("/api/v1/auth/logout", headers=_cookie("gone"))).status_code == 204


async def test_sessions_list_matches_the_fixture_and_marks_current(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine", ip="203.0.113.24")
    await world.add_session(user, "other", hours_ago=5)

    response = await client.get("/api/v1/account/sessions", headers=_cookie("mine"))

    assert response.status_code == 200
    items = response.json()
    assert [i["current"] for i in items] == [True, False]
    assert set(items[0]) == set(_fixture("AccountSessionList", "two")[0])
    assert items[0]["ip"] == "203.0.113.24"
    assert items[1]["ip"] is None
    assert hash_token("mine") not in json.dumps(items)


async def test_sessions_require_a_login(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    response = await client.get("/api/v1/account/sessions")

    assert response.status_code == 401
    assert response.json()["code"] == "auth_required"


async def test_sessions_do_not_leak_other_users(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    anna = await world.add_user()
    boris = await world.add_user("boris@example.org")
    await world.add_session(anna, "anna")
    await world.add_session(boris, "boris")

    items = (await client.get("/api/v1/account/sessions", headers=_cookie("anna"))).json()

    assert len(items) == 1


async def test_revoke_one_session(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")
    await world.add_session(user, "other", hours_ago=2)
    items = (await client.get("/api/v1/account/sessions", headers=_cookie("mine"))).json()
    other_id = next(i["id"] for i in items if not i["current"])

    response = await client.delete(f"/api/v1/account/sessions/{other_id}", headers=_cookie("mine"))

    assert response.status_code == 204
    assert await world.sessions.get(hash_token("other")) is None
    assert await world.sessions.get(hash_token("mine")) is not None
    assert "set-cookie" not in response.headers


async def test_revoke_current_session_clears_cookie(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")
    items = (await client.get("/api/v1/account/sessions", headers=_cookie("mine"))).json()

    response = await client.delete(f"/api/v1/account/sessions/{items[0]['id']}", headers=_cookie("mine"))

    assert response.status_code == 204
    assert "Max-Age=0" in response.headers["set-cookie"]


async def test_foreign_or_unknown_session_id_is_404(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    anna = await world.add_user()
    boris = await world.add_user("boris@example.org")
    await world.add_session(anna, "anna")
    await world.add_session(boris, "boris")
    foreign = (await client.get("/api/v1/account/sessions", headers=_cookie("boris"))).json()[0]["id"]

    assert (await client.delete(f"/api/v1/account/sessions/{foreign}", headers=_cookie("anna"))).status_code == 404
    assert (await client.delete("/api/v1/account/sessions/ses_nope", headers=_cookie("anna"))).status_code == 404
    assert await world.sessions.get(hash_token("boris")) is not None


async def test_revoke_other_sessions_keeps_current(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")
    await world.add_session(user, "o1", hours_ago=1)
    await world.add_session(user, "o2", hours_ago=2)

    response = await client.delete("/api/v1/account/sessions", headers=_cookie("mine"))

    assert response.status_code == 204
    assert await world.sessions.get(hash_token("mine")) is not None
    assert await world.sessions.get(hash_token("o1")) is None
    assert await world.sessions.get(hash_token("o2")) is None


async def test_local_mode_bootstrap_equals_the_local_fixture(tmp_path: Path) -> None:
    app = create_test_app(create_test_container(tmp_path / "data"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/session/bootstrap")

    body = response.json()
    assert response.status_code == 200
    assert body == {**_fixture("Bootstrap", "local"), "version": body["version"]}
    assert body["version"] == settings.get_app_version()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/auth/login"),
        ("POST", "/api/v1/auth/logout"),
        ("GET", "/api/v1/account/sessions"),
        ("DELETE", "/api/v1/account/sessions"),
        ("DELETE", "/api/v1/account/sessions/ses_x"),
    ],
)
async def test_local_mode_has_no_login_routes(tmp_path: Path, method: str, path: str) -> None:
    app = create_test_app(create_test_container(tmp_path / "data"))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(
            method, path, json={"email": "a@b.co", "password": "x"} if method == "POST" else None
        )

    assert response.status_code == 404
