"""Подтверждение почты, сброс пароля и смена e-mail по HTTP против эталонов contracts/server."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
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
from hse_doc_studio.core.identity.entities import MailKind, Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.account_email import ConfirmEmailChangeUC, RequestEmailChangeUC
from hse_doc_studio.use_cases.identity.mail import LinkDelivery
from hse_doc_studio.use_cases.identity.recovery import (
    ForgotPasswordUC,
    ResendVerificationUC,
    ResetPasswordUC,
    VerifyEmailUC,
)
from hse_doc_studio.use_cases.identity.sessions import SessionService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import (
    InMemoryAuditLog,
    InMemoryAuthTokenRepository,
    InMemoryMailOutboxRepository,
    InMemorySessionRepository,
    empty_bearer_resolver,
)
from tests.fakes.identity import InMemoryCredentialRepository, InMemoryIdentityStore, InMemoryUserRepository

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"
PASSWORD = "correct horse battery"
NEW_PASSWORD = "a much longer new passphrase"
NOW = datetime.now(UTC)
FORGOT = "neutral"


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


class _Sender:
    enabled = False

    async def send(self, to: str, subject: str, body: str) -> None:
        raise RuntimeError("no smtp")


class _World:
    def __init__(self) -> None:
        store = InMemoryIdentityStore()
        self.users = InMemoryUserRepository(store)
        self.creds = InMemoryCredentialRepository(store)
        self.sessions = InMemorySessionRepository()
        self.tokens = InMemoryAuthTokenRepository()
        self.outbox = InMemoryMailOutboxRepository()
        self.audit = InMemoryAuditLog()
        self.links: list[tuple[MailKind, str]] = []

    async def add_user(self, email: str = "anna.petrova@example.org", *, verified: bool = True) -> User:
        user = User(
            id="u1",
            email=email,
            email_normalized=normalize_email(email),
            name="Анна Петрова",
            status=UserStatus.active,
            created_at=NOW,
            email_verified=verified,
            locale="ru",
        )
        await self.users.add(user)
        await self.creds.set_hash(user.id, _Hasher().hash(PASSWORD))
        return replace(user)

    async def add_session(self, secret: str = "secret") -> None:
        await self.sessions.add(
            Session(hash_token(secret), "u1", f"csrf-{secret}", NOW, NOW, NOW + timedelta(days=7), None, "UA")
        )

    async def outbox_token(self, kind: MailKind) -> str:
        (link,) = [link for k, link in self.links if k is kind]
        return link.rpartition("/")[2]


class _RecordingDelivery(LinkDelivery):
    """В outbox ссылок нет, а тесту нужен токен из письма."""

    def __init__(self, world: _World) -> None:
        super().__init__(_Sender(), world.outbox)
        self._world = world

    async def deliver(self, kind: MailKind, to_email: str, link: str, now: datetime, **kwargs: Any) -> str | None:
        self._world.links.append((kind, link))
        return await super().deliver(kind, to_email, link, now, **kwargs)


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, world: _World) -> None:
        super().__init__()
        self._w = world
        self._delivery = _RecordingDelivery(world)
        self._url = "https://studio.test"

    @provide
    def resolver(self) -> IActorResolver:
        service = SessionService(self._w.sessions, self._w.users)
        return ChainActorResolver([SessionCookieResolver(service), empty_bearer_resolver()])

    @provide
    def verify(self) -> VerifyEmailUC:
        return VerifyEmailUC(self._w.users, self._w.tokens, self._w.audit, _Uow())

    @provide
    def resend(self) -> ResendVerificationUC:
        w = self._w
        return ResendVerificationUC(w.users, w.tokens, self._delivery, w.audit, _Uow(), public_url=self._url)

    @provide
    def forgot(self) -> ForgotPasswordUC:
        w = self._w
        return ForgotPasswordUC(w.users, w.tokens, self._delivery, w.audit, _Uow(), public_url=self._url)

    @provide
    def reset(self) -> ResetPasswordUC:
        w = self._w
        return ResetPasswordUC(w.users, w.creds, w.tokens, w.sessions, _Hasher(), w.audit, _Uow())

    @provide
    def change(self) -> RequestEmailChangeUC:
        w = self._w
        return RequestEmailChangeUC(
            w.users, w.creds, w.tokens, self._delivery, _Hasher(), w.audit, _Uow(), public_url=self._url
        )

    @provide
    def confirm(self) -> ConfirmEmailChangeUC:
        w = self._w
        return ConfirmEmailChangeUC(w.users, w.tokens, w.audit, _Uow())


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


async def test_forgot_answers_the_same_for_known_and_unknown_addresses(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()

    known = await client.post("/api/v1/auth/forgot", json={"email": "Anna.Petrova@example.org"})
    unknown = await client.post("/api/v1/auth/forgot", json={"email": "ghost@example.org"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json() == _fixture("ForgotResponse", FORGOT)
    assert known.headers["cache-control"] == unknown.headers["cache-control"] == "no-store"
    assert [e.to_email for e in await world.outbox.list_active(NOW)] == ["anna.petrova@example.org"]


async def test_reset_changes_the_password_and_the_link_dies(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()
    await world.add_session()
    await client.post("/api/v1/auth/forgot", json={"email": "anna.petrova@example.org"})
    token = await world.outbox_token(MailKind.reset_password)

    done = await client.post("/api/v1/auth/reset", json={"token": token, "password": NEW_PASSWORD})
    again = await client.post("/api/v1/auth/reset", json={"token": token, "password": NEW_PASSWORD})

    assert done.status_code == 204
    assert await world.creds.get_hash("u1") == f"h:{NEW_PASSWORD}"
    assert await world.sessions.list_for_user("u1") == []
    assert again.status_code == 422
    assert again.json()["code"] == "token_invalid"


async def test_reset_with_a_weak_password_keeps_the_error_shape(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()
    await client.post("/api/v1/auth/forgot", json={"email": "anna.petrova@example.org"})
    token = await world.outbox_token(MailKind.reset_password)

    response = await client.post("/api/v1/auth/reset", json={"token": token, "password": "short"})

    assert response.status_code == 422
    assert response.json()["code"] == "password_policy"
    assert set(response.json()) == set(_fixture("AuthErrorBody", "password_policy"))


async def test_verify_flow_and_neutral_resend(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user(verified=False)

    resend = await client.post("/api/v1/auth/verify/resend", json={"email": "anna.petrova@example.org"})
    ghost = await client.post("/api/v1/auth/verify/resend", json={"email": "ghost@example.org"})
    assert resend.json() == ghost.json() == _fixture("ForgotResponse", FORGOT)

    token = await world.outbox_token(MailKind.verify_email)
    assert (await client.post("/api/v1/auth/verify", json={"token": token})).status_code == 204
    user = await world.users.get("u1")
    assert user is not None
    assert user.email_verified
    bad = await client.post("/api/v1/auth/verify", json={"token": token})
    assert (bad.status_code, bad.json()["code"]) == (422, "token_invalid")


async def test_email_change_needs_login_and_password(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()
    await world.add_session()
    body = _fixture("ChangeEmailRequest", "new_address")

    anonymous = await client.post("/api/v1/account/email", json=body)
    wrong = await client.post("/api/v1/account/email", json={**body, "password": "wrong"}, headers=_cookie("secret"))
    bad_address = await client.post(
        "/api/v1/account/email", json={**body, "email": "not-an-email"}, headers=_cookie("secret")
    )

    assert anonymous.status_code == 401
    assert (wrong.status_code, wrong.json()["code"]) == (401, "invalid_credentials")
    assert bad_address.status_code == 422


async def test_email_change_round_trip(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()
    await world.add_session()
    body = {**_fixture("ChangeEmailRequest", "new_address"), "password": PASSWORD}

    response = await client.post("/api/v1/account/email", json=body, headers=_cookie("secret"))

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == set(_fixture("ChangeEmailResponse", "link_only"))
    assert payload["status"] == "check_email"
    # Ссылка не возвращается запросившему даже без SMTP: иначе он «подтвердил» бы чужой адрес.
    assert payload["link"] is None
    token = await world.outbox_token(MailKind.email_change)
    confirm = await client.post("/api/v1/account/email/confirm", json={"token": token})
    assert confirm.status_code == 204
    user = await world.users.get("u1")
    assert user is not None
    assert user.email == body["email"]
    again = await client.post("/api/v1/account/email/confirm", json={"token": token})
    assert again.json()["code"] == "token_invalid"
