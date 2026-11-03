"""Passkey через HTTP: регистрация в профиле, вход без пароля, повторное подтверждение и админка против эталонов."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
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
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.identity.auth_settings import KEY_PASSKEYS_ENABLED
from hse_doc_studio.core.identity.entities import RegistrationInvite, Session, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.infra.identity.webauthn import PyWebAuthn
from hse_doc_studio.use_cases.admin.passkeys import ListUserPasskeysUC, ResetUserPasskeysUC
from hse_doc_studio.use_cases.admin.settings import GetAuthGroupUC, UpdateAuthMethodsUC
from hse_doc_studio.use_cases.identity.auth_settings import AuthSettingsService, UpdateAuthSettingsUC
from hse_doc_studio.use_cases.identity.passkey_ceremony import PasskeyChallenges, PasskeyPolicy
from hse_doc_studio.use_cases.identity.passkey_login import AssertionChecker, FinishPasskeyLoginUC, StartPasskeyLoginUC
from hse_doc_studio.use_cases.identity.passkey_signup import FinishPasskeySignupUC, StartPasskeySignupUC
from hse_doc_studio.use_cases.identity.passkeys import (
    DeletePasskeyUC,
    FinishPasskeyRegistrationUC,
    ListPasskeysUC,
    LoginMethods,
    RenamePasskeyUC,
    StartPasskeyRegistrationUC,
)
from hse_doc_studio.use_cases.identity.reauth import ReauthUC, StartReauthUC
from hse_doc_studio.use_cases.identity.sessions import SessionService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import (
    InMemoryAuditLog,
    InMemoryAuthTokenRepository,
    InMemoryLoginAttemptRepository,
    InMemoryOidcProviderRepository,
    InMemoryRegistrationInviteRepository,
    InMemorySessionRepository,
    empty_bearer_resolver,
)
from tests.fakes.authenticator import SoftAuthenticator
from tests.fakes.identity import (
    InMemoryCredentialRepository,
    InMemoryIdentityStore,
    InMemoryInstanceSettingsRepository,
    InMemoryUserRepository,
)
from tests.fakes.ops import NoopUow
from tests.fakes.passkeys import InMemoryPasskeyRepository

ORIGIN = "http://localhost:8100"
PASSWORD = "correct horse battery"
_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"


def _fixture(schema: str, name: str) -> Any:
    return json.loads((_FIXTURES / schema / f"{name}.json").read_text(encoding="utf-8"))


class _Hasher:
    def hash(self, password: str) -> str:
        return f"h:{password}"

    def verify(self, password: str, password_hash: str) -> bool:
        return password_hash == f"h:{password}"

    def needs_rehash(self, password_hash: str) -> bool:  # noqa: ARG002
        return False


class _World:
    def __init__(self) -> None:
        self.store = InMemoryIdentityStore()
        self.users = InMemoryUserRepository(self.store)
        self.creds = InMemoryCredentialRepository(self.store)
        self.sessions = InMemorySessionRepository()
        self.tokens = InMemoryAuthTokenRepository()
        self.attempts = InMemoryLoginAttemptRepository()
        self.audit = InMemoryAuditLog()
        self.settings = InMemoryInstanceSettingsRepository()
        self.passkeys = InMemoryPasskeyRepository()
        self.invites = InMemoryRegistrationInviteRepository()
        self.phone = SoftAuthenticator(origin=ORIGIN)

    async def add_user(self, uid: str = "ann", *, password: bool = True, admin: bool = False) -> User:
        email = f"{uid}@example.org"
        user = User(
            id=uid,
            email=email,
            email_normalized=normalize_email(email),
            name=uid.title(),
            status=UserStatus.active,
            created_at=datetime.now(UTC),
            email_verified=True,
            is_instance_admin=admin,
        )
        await self.users.add(user)
        if password:
            await self.creds.set_hash(uid, _Hasher().hash(PASSWORD))
        return user

    async def cookie(self, user: User, *, minutes_ago: int = 0) -> dict[str, str]:
        now = datetime.now(UTC)
        opened = now - timedelta(minutes=minutes_ago)
        secret = f"s-{user.id}-{minutes_ago}"
        await self.sessions.add(
            Session(hash_token(secret), user.id, "csrf", opened, opened, now + timedelta(days=1), None, "UA")
        )
        return {"Cookie": f"{SESSION_COOKIE}={secret}"}


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, w: _World) -> None:
        super().__init__()
        self.w = w
        auth = AuthSettingsService(w.settings)
        uow = NoopUow()
        webauthn = PyWebAuthn()
        challenges = PasskeyChallenges(w.tokens)
        policy = PasskeyPolicy(auth)
        methods = LoginMethods(w.users, w.creds, w.passkeys, auth)
        checker = AssertionChecker(w.passkeys, challenges, webauthn)
        oidc = InMemoryOidcProviderRepository()
        group = GetAuthGroupUC(auth, oidc, w.passkeys)
        update = UpdateAuthSettingsUC(auth, w.settings, w.audit, uow)
        instances: dict[type, object] = {
            ListPasskeysUC: ListPasskeysUC(w.passkeys, methods, policy),
            StartPasskeyRegistrationUC: StartPasskeyRegistrationUC(
                w.users, w.passkeys, w.sessions, challenges, policy, webauthn
            ),
            FinishPasskeyRegistrationUC: FinishPasskeyRegistrationUC(
                w.users, w.passkeys, challenges, policy, webauthn, w.audit, uow
            ),
            RenamePasskeyUC: RenamePasskeyUC(w.passkeys, w.audit),
            DeletePasskeyUC: DeletePasskeyUC(w.users, w.passkeys, w.sessions, methods, w.audit, uow),
            StartPasskeyLoginUC: StartPasskeyLoginUC(challenges, policy, webauthn),
            FinishPasskeyLoginUC: FinishPasskeyLoginUC(w.users, w.passkeys, w.sessions, checker, policy, w.audit, uow),
            StartReauthUC: StartReauthUC(w.passkeys, challenges, policy, webauthn),
            ReauthUC: ReauthUC(
                w.sessions, w.creds, _Hasher(), w.attempts, w.passkeys, checker, policy, auth, w.audit, uow
            ),
            ListUserPasskeysUC: ListUserPasskeysUC(w.users, w.passkeys),
            ResetUserPasskeysUC: ResetUserPasskeysUC(w.users, w.passkeys, w.audit, uow),
            StartPasskeySignupUC: StartPasskeySignupUC(w.invites, w.users, challenges, policy, webauthn),
            FinishPasskeySignupUC: FinishPasskeySignupUC(
                w.invites, w.users, w.passkeys, w.sessions, challenges, policy, webauthn, w.audit, uow
            ),
            GetAuthGroupUC: group,
            UpdateAuthMethodsUC: UpdateAuthMethodsUC(update, auth, oidc, group),
        }
        for kind, instance in instances.items():
            self._register(kind, instance)

    def _register(self, kind: type, instance: object) -> None:
        self.provide(lambda: instance, provides=kind)

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver(
            [SessionCookieResolver(SessionService(self.w.sessions, self.w.users)), empty_bearer_resolver()]
        )


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, _World]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(settings.auth, "public_url", ORIGIN)
    world = _World()
    app = FastAPI()
    app.include_router(api_router)
    app.include_router(make_admin_router())
    install_exception_handlers(app)
    container = make_async_container(_Provider(world), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        yield client, world
    await container.close()


async def _register(client: AsyncClient, world: _World, cookie: dict[str, str], name: str | None = "Телефон") -> Any:
    options = await client.post("/api/v1/account/passkeys/options", headers=cookie)
    assert options.status_code == 200, options.text
    credential = world.phone.create(options.json()["options"])
    created = await client.post(
        "/api/v1/account/passkeys", json={"name": name, "credential": credential}, headers=cookie
    )
    assert created.status_code == 201, created.text
    return created.json()


def _shape(schema: str, name: str) -> set[str]:
    return set(_fixture(schema, name))


async def test__register_then_list__matches_contract(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    cookie = await world.cookie(await world.add_user())

    created = await _register(client, world, cookie)
    listed = await client.get("/api/v1/account/passkeys", headers=cookie)

    assert set(created) == _shape("AccountPasskey", "synced")
    assert (created["name"], created["domain"], created["domain_matches"]) == ("Телефон", "localhost", True)
    body = listed.json()
    assert listed.headers["cache-control"] == "no-store"
    assert set(body) == _shape("AccountPasskeyList", "with_keys")
    assert (body["enabled"], body["domain"], body["has_password"], body["limit"]) == (True, "localhost", True, 20)
    assert [k["id"] for k in body["items"]] == [created["id"]]


async def test__login_by_passkey__sets_session_cookie(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await _register(client, world, await world.cookie(user))

    options = await client.post("/api/v1/auth/passkey/options")
    login = await client.post(
        "/api/v1/auth/passkey/login", json={"credential": world.phone.get(options.json()["options"])}
    )

    assert options.status_code == 200
    assert options.json()["options"]["rpId"] == "localhost"
    assert login.status_code == 200, login.text
    assert set(login.json()) == {"user", "csrf_token"}
    assert login.json()["user"]["id"] == user.id
    assert login.headers["cache-control"] == "no-store"
    secret = login.cookies.get(SESSION_COOKIE)
    assert secret
    me = await client.get("/api/v1/account/passkeys", headers={"Cookie": f"{SESSION_COOKIE}={secret}"})
    assert me.status_code == 200


async def test__login__forged_assertion__401_passkey_invalid(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await _register(client, world, await world.cookie(await world.add_user()))
    options = (await client.post("/api/v1/auth/passkey/options")).json()["options"]

    forged = world.phone.get(options, origin="https://phish.example")
    response = await client.post("/api/v1/auth/passkey/login", json={"credential": forged})

    assert (response.status_code, response.json()["code"]) == (401, "passkey_invalid")
    assert SESSION_COOKIE not in response.cookies


async def test__register__stale_session__reauth_by_password_then_allowed(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    cookie = await world.cookie(await world.add_user(), minutes_ago=60)

    refused = await client.post("/api/v1/account/passkeys/options", headers=cookie)
    wrong = await client.post("/api/v1/account/reauth", json={"password": "nope", "credential": None}, headers=cookie)
    ok = await client.post("/api/v1/account/reauth", json={"password": PASSWORD, "credential": None}, headers=cookie)
    allowed = await client.post("/api/v1/account/passkeys/options", headers=cookie)

    assert (refused.status_code, refused.json()["code"]) == (403, "reauth_required")
    assert (wrong.status_code, wrong.json()["code"]) == (401, "invalid_credentials")
    assert ok.status_code == 200
    assert set(ok.json()) == _shape("ReauthResponse", "ok")
    assert allowed.status_code == 200


async def test__reauth_by_passkey__opens_window(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user(password=False)
    await _register(client, world, await world.cookie(user))
    stale = await world.cookie(user, minutes_ago=60)

    options = await client.post("/api/v1/account/reauth/options", headers=stale)
    credential = world.phone.get(options.json()["options"])
    ok = await client.post("/api/v1/account/reauth", json={"password": None, "credential": credential}, headers=stale)

    assert options.json()["options"]["allowCredentials"][0]["id"] == world.phone.credentials[0].id
    assert ok.status_code == 200, ok.text
    assert (await client.post("/api/v1/account/passkeys/options", headers=stale)).status_code == 200


async def test__reauth__both_or_none__422(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    cookie = await world.cookie(await world.add_user())

    both = await client.post("/api/v1/account/reauth", json={"password": PASSWORD, "credential": {}}, headers=cookie)
    none = await client.post("/api/v1/account/reauth", json={"password": None, "credential": None}, headers=cookie)

    assert both.status_code == none.status_code == 422


async def test__delete__last_method_409_then_rename_and_delete_with_second_key(
    env: tuple[AsyncClient, _World],
) -> None:
    client, world = env
    user = await world.add_user(password=False)
    cookie = await world.cookie(user)
    first = await _register(client, world, cookie)

    last = await client.delete(f"/api/v1/account/passkeys/{first['id']}", headers=cookie)
    world.phone = SoftAuthenticator(origin=ORIGIN)
    second = await _register(client, world, cookie, name=None)
    renamed = await client.patch(f"/api/v1/account/passkeys/{second['id']}", json={"name": "YubiKey"}, headers=cookie)
    deleted = await client.delete(f"/api/v1/account/passkeys/{first['id']}", headers=cookie)

    assert (last.status_code, last.json()["code"]) == (409, "last_login_method")
    assert second["name"] == "Passkey"
    assert renamed.json()["name"] == "YubiKey"
    assert deleted.status_code == 204
    names = [k["name"] for k in (await client.get("/api/v1/account/passkeys", headers=cookie)).json()["items"]]
    assert names == ["YubiKey"]


async def test__registration__bad_response__422(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    cookie = await world.cookie(await world.add_user())
    options = (await client.post("/api/v1/account/passkeys/options", headers=cookie)).json()["options"]

    credential = world.phone.create(options, uv=False)
    response = await client.post(
        "/api/v1/account/passkeys", json={"name": None, "credential": credential}, headers=cookie
    )

    assert (response.status_code, response.json()["code"]) == (422, "passkey_invalid")


async def test__anonymous__account_routes_401(env: tuple[AsyncClient, _World]) -> None:
    client, _ = env

    for method, path in (
        ("GET", "/api/v1/account/passkeys"),
        ("POST", "/api/v1/account/passkeys/options"),
        ("POST", "/api/v1/account/reauth/options"),
    ):
        assert (await client.request(method, path)).status_code == 401, path


async def test__disabled_by_admin__403_passkeys_disabled(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    cookie = await world.cookie(await world.add_user())
    await world.settings.set(KEY_PASSKEYS_ENABLED, False, source="admin")

    login = await client.post("/api/v1/auth/passkey/options")
    register = await client.post("/api/v1/account/passkeys/options", headers=cookie)
    listed = (await client.get("/api/v1/account/passkeys", headers=cookie)).json()

    assert (login.status_code, login.json()["code"]) == (403, "passkeys_disabled")
    assert (register.status_code, register.json()["code"]) == (403, "passkeys_disabled")
    assert listed["enabled"] is False


async def test__insecure_public_url__passkeys_unavailable(
    env: tuple[AsyncClient, _World], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _ = env
    monkeypatch.setattr(settings.auth, "public_url", "http://studio.example.org")

    response = await client.post("/api/v1/auth/passkey/options")

    assert (response.status_code, response.json()["code"]) == (403, "passkeys_disabled")


async def test__admin__sees_and_resets_keys_of_a_person(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    ann = await world.add_user()
    await _register(client, world, await world.cookie(ann))
    boss = await world.cookie(await world.add_user("boss", admin=True))
    student = await world.cookie(await world.add_user("bob"))

    listed = await client.get(f"/api/admin/users/{ann.id}/passkeys", headers=boss)
    stranger = await client.get(f"/api/admin/users/{ann.id}/passkeys", headers=student)
    reset = await client.delete(f"/api/admin/users/{ann.id}/passkeys", headers=boss)
    after = await client.get(f"/api/admin/users/{ann.id}/passkeys", headers=boss)

    assert listed.status_code == 200
    assert set(listed.json()["items"][0]) == set(_fixture("AdminUserPasskeyList", "two_keys")["items"][0])
    assert stranger.status_code == 404
    assert reset.json() == {"removed": 1}
    assert after.json() == {"items": []}
    assert [e.action for e in await world.audit.list(action="admin.passkeys_reset")] == ["admin.passkeys_reset"]


async def test__admin_auth_settings__domain_counts_and_toggle(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await _register(client, world, await world.cookie(await world.add_user()))
    boss = await world.cookie(await world.add_user("boss", admin=True))

    shown = (await client.get("/api/admin/settings/auth", headers=boss)).json()
    off = await client.put("/api/admin/settings/auth", json={"passkeys_enabled": False}, headers=boss)

    assert set(shown) == set(_fixture("AdminAuthSettings", "password_only"))
    assert (shown["passkeys_enabled"], shown["passkey_domain"], shown["passkey_issue"]) == (True, "localhost", None)
    assert shown["passkey_domains"] == [{"domain": "localhost", "count": 1}]
    assert shown["fields"]["auth.passkeys_enabled"] == {"source": "default", "locked": False}
    assert off.json()["passkeys_enabled"] is False
    assert off.json()["fields"]["auth.passkeys_enabled"] == {"source": "admin", "locked": False}


async def _invite(world: _World, token: str, email: str | None) -> None:
    await world.invites.add(
        RegistrationInvite(
            token_hash=hash_token(token),
            email=email,
            created_by="boss",
            expires_at=datetime.now(UTC) + timedelta(days=1),
            id=f"inv-{token}",
        )
    )


async def test__signup_by_invite_with_passkey__session_and_contract(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await _invite(world, "tok", "new@example.org")
    body = _fixture("PasskeySignupOptionsRequest", "invite")
    body["invitation_token"] = "tok"

    options = await client.post("/api/v1/auth/register/passkey/options", json=body)
    request = _fixture("PasskeySignupRequest", "invite")
    request.update(invitation_token="tok", credential=world.phone.create(options.json()["options"]))
    created = await client.post("/api/v1/auth/register/passkey", json=request)

    assert options.status_code == 200, options.text
    assert created.status_code == 200, created.text
    assert created.json()["user"]["email"] == "new@example.org"
    secret = created.cookies.get(SESSION_COOKIE)
    listed = await client.get("/api/v1/account/passkeys", headers={"Cookie": f"{SESSION_COOKIE}={secret}"})
    assert [(k["name"], k["domain_matches"]) for k in listed.json()["items"]] == [("Chrome · macOS", True)]
    assert listed.json()["has_password"] is False


async def test__signup__invite_without_address_403_and_taken_address_409(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await _invite(world, "any", None)
    await world.add_user("taken")
    await _invite(world, "taken", "taken@example.org")

    anyone = await client.post("/api/v1/auth/register/passkey/options", json={"invitation_token": "any", "name": "A"})
    taken = await client.post("/api/v1/auth/register/passkey/options", json={"invitation_token": "taken", "name": "T"})

    assert (anyone.status_code, anyone.json()["code"]) == (403, "invitation_invalid")
    assert (taken.status_code, taken.json()["code"]) == (409, "email_taken")
