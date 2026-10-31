"""Регистрация, карточка приглашения и смена пароля по HTTP против эталонов contracts/server."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
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
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.auth_settings import KEY_REGISTRATION_MODE
from hse_doc_studio.core.identity.entities import Session
from hse_doc_studio.core.identity.normalize import hash_token
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.change_password import ChangePasswordUC
from hse_doc_studio.use_cases.identity.invites import InvitationInfoUC
from hse_doc_studio.use_cases.identity.register import RegisterUC
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.unit.use_cases.identity.conftest import T0, FakeSender, World

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"
PASSWORD = "correct horse battery"
NEW_PASSWORD = "a much longer new passphrase"


def _fixture(schema: str, name: str) -> Any:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, w: World) -> None:
        super().__init__()
        self._w = w

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver([SessionCookieResolver(self._w.service()), empty_bearer_resolver()])

    @provide
    def register(self) -> RegisterUC:
        return self._w.register_uc()

    @provide
    def invitation(self) -> InvitationInfoUC:
        return self._w.invitation_info_uc()

    @provide
    def change(self) -> ChangePasswordUC:
        return self._w.change_uc()


@pytest_asyncio.fixture
async def env(world: World, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, World]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    app = FastAPI()
    app.include_router(api_router)
    install_exception_handlers(app)
    container = make_async_container(_Provider(world), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, world
    await container.close()


async def _login(world: World, secret: str = "secret") -> dict[str, str]:
    await world.sessions.add(
        Session(hash_token(secret), "u1", f"csrf-{secret}", T0, T0, T0.replace(year=T0.year + 1), None, "UA")
    )
    return {"Cookie": f"{SESSION_COOKIE}={secret}"}


async def test_open_registration_answers_with_the_contract_shape(env: tuple[AsyncClient, World]) -> None:
    client, world = env
    await world.settings.set(KEY_REGISTRATION_MODE, "open", source="test")
    world.sender = FakeSender(enabled=True)

    response = await client.post("/api/v1/auth/register", json=_fixture("RegisterRequest", "open"))

    assert response.status_code == 200
    assert set(response.json()) == set(_fixture("RegisterResponse", "check_email"))
    assert response.json()["status"] == "check_email"
    assert await world.users.get_by_email(_fixture("RegisterRequest", "open")["email"]) is not None


async def test_open_registration_without_smtp_is_refused(env: tuple[AsyncClient, World]) -> None:
    """Без SMTP открытая регистрация не создаёт аккаунт: по почте её не подтвердить, нужно приглашение."""
    client, world = env
    await world.settings.set(KEY_REGISTRATION_MODE, "open", source="test")
    assert not world.sender.enabled
    body = _fixture("RegisterRequest", "open")

    response = await client.post("/api/v1/auth/register", json=body)

    assert (response.status_code, response.json()["code"]) == (403, "invitation_required")
    assert await world.users.get_by_email(body["email"]) is None


async def test_register_never_returns_the_verify_link_even_without_smtp(env: tuple[AsyncClient, World]) -> None:
    """Приглашение без привязки к адресу тоже создаёт ссылку без SMTP, но HTTP-ответ её не отдаёт."""
    client, world = env
    await world.add_user("admin@example.org", user_id="admin")
    created = await world.create_invite_uc().execute(Actor.user("admin", is_instance_admin=True))
    assert not world.sender.enabled
    body = {**_fixture("RegisterRequest", "open"), "invitation_token": created.token}

    response = await client.post("/api/v1/auth/register", json=body)

    assert response.status_code == 200
    assert response.json()["link"] is None


async def test_closed_registration_is_refused_with_a_code(env: tuple[AsyncClient, World]) -> None:
    client, world = env
    await world.settings.set(KEY_REGISTRATION_MODE, "closed", source="test")

    response = await client.post("/api/v1/auth/register", json=_fixture("RegisterRequest", "open"))

    assert (response.status_code, response.json()["code"]) == (403, "registration_closed")


async def test_invitation_lookup_and_registration_by_invite(env: tuple[AsyncClient, World]) -> None:
    client, world = env
    await world.settings.set(KEY_REGISTRATION_MODE, "invite", source="test")
    await world.add_user("admin@example.org", user_id="admin")
    created = await world.create_invite_uc().execute(
        Actor.user("admin", is_instance_admin=True), email="maria@example.org"
    )

    info = await client.get(f"/api/v1/auth/invitations/{created.token}")
    bad = await client.get("/api/v1/auth/invitations/nope")
    done = await client.post(
        "/api/v1/auth/register",
        json={"email": "maria@example.org", "name": "Мария", "password": PASSWORD, "invitation_token": created.token},
    )

    assert info.status_code == 200
    assert set(info.json()) == set(_fixture("InvitationInfo", "plain"))
    assert info.json()["email"] == "maria@example.org"
    assert (bad.status_code, bad.json()["code"]) == (403, "invitation_invalid")
    assert done.status_code == 200
    assert done.json()["status"] == "check_email"


async def test_change_password_needs_login_and_the_current_password(env: tuple[AsyncClient, World]) -> None:
    client, world = env
    await world.add_user()
    headers = await _login(world)
    body = {"current_password": PASSWORD, "new_password": NEW_PASSWORD, "sign_out_other_sessions": True}

    anonymous = await client.post("/api/v1/account/password", json=body)
    wrong = await client.post("/api/v1/account/password", json={**body, "current_password": "wrong"}, headers=headers)
    weak = await client.post("/api/v1/account/password", json={**body, "new_password": "short"}, headers=headers)
    done = await client.post("/api/v1/account/password", json=body, headers=headers)

    assert anonymous.status_code == 401
    assert (wrong.status_code, wrong.json()["code"]) == (401, "invalid_credentials")
    assert (weak.status_code, weak.json()["code"]) == (422, "password_policy")
    assert done.status_code == 204
    assert await world.creds.get_hash("u1") == world.hasher.hash(NEW_PASSWORD)


async def test_change_password_keeps_other_sessions_when_asked(env: tuple[AsyncClient, World]) -> None:
    client, world = env
    await world.add_user()
    headers = await _login(world)
    await _login(world, "other")

    done = await client.post(
        "/api/v1/account/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD, "sign_out_other_sessions": False},
        headers=headers,
    )

    assert done.status_code == 204
    assert len(await world.sessions.list_for_user("u1")) == 2
