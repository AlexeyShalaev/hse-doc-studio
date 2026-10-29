"""GET и PATCH /account против эталонов contracts/server: профиль и подпись коммитов."""

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
from hse_doc_studio.api.schemas.session import AccountProfile
from hse_doc_studio.core.identity.entities import Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.account_profile import GetAccountUC, UpdateAccountUC
from hse_doc_studio.use_cases.identity.sessions import SessionService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemoryAuditLog, InMemorySessionRepository
from tests.fakes.identity import InMemoryIdentityStore, InMemoryUserRepository

_FIXTURES = Path(__file__).resolve().parents[5].parent / "contracts" / "server" / "fixtures"
NOW = datetime.now(UTC)
DOMAIN = "noreply.studio.example.org"


def _fixture(schema: str, name: str) -> Any:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


class _World:
    def __init__(self) -> None:
        self.users = InMemoryUserRepository(InMemoryIdentityStore())
        self.sessions = InMemorySessionRepository()
        self.audit = InMemoryAuditLog()

    async def add_user(self, user_id: str, name: str, email: str, secret: str, locale: str | None = "ru") -> None:
        await self.users.add(
            User(
                id=user_id,
                email=email,
                email_normalized=normalize_email(email),
                name=name,
                status=UserStatus.active,
                created_at=NOW,
                email_verified=True,
                locale=locale,
            )
        )
        await self.sessions.add(
            Session(hash_token(secret), user_id, f"csrf-{secret}", NOW, NOW, NOW + timedelta(days=7), None, "UA")
        )


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, world: _World) -> None:
        super().__init__()
        self._w = world

    @provide
    def resolver(self) -> IActorResolver:
        service = SessionService(self._w.sessions, self._w.users)
        return ChainActorResolver([SessionCookieResolver(service, DOMAIN), BearerActorResolver()])

    @provide
    def get_uc(self) -> GetAccountUC:
        return GetAccountUC(self._w.users, DOMAIN)

    @provide
    def update_uc(self) -> UpdateAccountUC:
        return UpdateAccountUC(self._w.users, self._w.audit, _Uow(), DOMAIN)


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, _World]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    world = _World()
    await world.add_user("u_01hx7k2m9c", "Анна Петрова", "anna.petrova@example.org", "anna")
    await world.add_user("u_01hx7k1a0b", "Иван Сидоров", "ivan.sidorov@example.org", "ivan", locale="en")
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


async def test_get_account_matches_the_contract_and_defaults_to_noreply(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    response = await client.get("/api/v1/account", headers=_cookie("anna"))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == _fixture("AccountProfile", "noreply_default")
    AccountProfile.model_validate(response.json())


async def test_anonymous_gets_401(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    assert (await client.get("/api/v1/account")).status_code == 401
    assert (await client.patch("/api/v1/account", json={"name": "X"})).status_code == 401


async def test_patch_sets_own_commit_identity(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    response = await client.patch(
        "/api/v1/account",
        json={"commit_name": "Ivan Sidorov", "commit_email": "ivan@personal.example.com"},
        headers=_cookie("ivan"),
    )

    assert response.status_code == 200
    assert response.json() == _fixture("AccountProfile", "own_commit_identity")


async def test_patch_contract_fixture_is_accepted_and_opt_in_shows_the_account_email(
    env: tuple[AsyncClient, _World],
) -> None:
    client, _ = env

    response = await client.patch(
        "/api/v1/account", json=_fixture("UpdateAccountRequest", "commit_identity"), headers=_cookie("anna")
    )

    body = response.json()
    assert response.status_code == 200
    assert (body["effective_commit_name"], body["effective_commit_email"]) == ("Анна П.", "anna.petrova@example.org")
    assert body["commit_email_is_noreply"] is False
    assert body["name"] == "Анна Петрова"
    assert body["locale"] == "ru"


async def test_patch_only_touches_sent_fields_and_empty_string_resets_commit_fields(
    env: tuple[AsyncClient, _World],
) -> None:
    client, _ = env
    await client.patch("/api/v1/account", json={"commit_email": "a@home.example"}, headers=_cookie("anna"))

    renamed = await client.patch("/api/v1/account", json={"name": "Анна П-И", "locale": "en"}, headers=_cookie("anna"))
    reset = await client.patch("/api/v1/account", json={"commit_email": ""}, headers=_cookie("anna"))

    assert renamed.json()["commit_email"] == "a@home.example"
    assert (renamed.json()["name"], renamed.json()["locale"]) == ("Анна П-И", "en")
    assert reset.json()["commit_email"] is None
    assert reset.json()["commit_email_is_noreply"] is True


async def test_invalid_commit_identity_keeps_the_profile_422_shape(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    response = await client.patch(
        "/api/v1/account", json={"commit_name": "<>", "commit_email": "nope"}, headers=_cookie("anna")
    )

    assert response.status_code == 422
    assert {(d["loc"][1], d["code"]) for d in response.json()["detail"]} == {
        ("commit_name", "commit_name_invalid"),
        ("commit_email", "commit_email_invalid"),
    }
    assert (await client.get("/api/v1/account", headers=_cookie("anna"))).json() == _fixture(
        "AccountProfile", "noreply_default"
    )


async def test_users_do_not_see_each_others_identity(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env
    await client.patch("/api/v1/account", json={"commit_name": "Only Ivan"}, headers=_cookie("ivan"))

    anna = (await client.get("/api/v1/account", headers=_cookie("anna"))).json()
    ivan = (await client.get("/api/v1/account", headers=_cookie("ivan"))).json()

    assert anna["effective_commit_name"] == "Анна Петрова"
    assert ivan["effective_commit_name"] == "Only Ivan"
    assert anna["effective_commit_email"] != ivan["effective_commit_email"]


async def test_unknown_field_is_rejected(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    response = await client.patch("/api/v1/account", json={"is_instance_admin": True}, headers=_cookie("anna"))

    assert response.status_code == 422
