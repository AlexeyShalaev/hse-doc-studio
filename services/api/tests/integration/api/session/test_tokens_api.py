"""Персональные токены доступа: выпуск, показ один раз, Bearer на API, смена прав, отзыв и запрет управлять
токенами токеном."""

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
from fastapi import APIRouter, Depends, FastAPI
from hse_doc_studio.api import route_scopes
from hse_doc_studio.api.auth_cookie import SESSION_COOKIE
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers, project_access_guard
from hse_doc_studio.api.route_scopes import ROUTE_SCOPES, RouteScope
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.identity.entities import ApiToken, ApiTokenOrigin, Session, TokenScope, User, UserStatus
from hse_doc_studio.core.identity.normalize import hash_token, normalize_email
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.resolvers import BearerActorResolver, ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.admin.lifecycle import ExportMyDataUC
from hse_doc_studio.use_cases.identity.api_tokens import (
    CreateApiTokenUC,
    ListApiTokensUC,
    RevokeApiTokenUC,
    UpdateApiTokenScopesUC,
)
from hse_doc_studio.use_cases.identity.sessions import ListSessionsUC, SessionService
from hse_doc_studio.use_cases.server_setup.state import KEY_SETUP_COMPLETED
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import InMemoryApiTokenRepository, InMemoryAuditLog, InMemorySessionRepository
from tests.fakes.identity import InMemoryIdentityStore, InMemoryInstanceSettingsRepository, InMemoryUserRepository
from tests.fakes.lifecycle import InMemoryUserLifecycle

_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "server" / "fixtures"
NOW = datetime.now(UTC)
CREATE = {"name": "CLI на ноутбуке", "scopes": ["api", "git:read"], "expires_in_days": 90}


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


class _World:
    def __init__(self) -> None:
        store = InMemoryIdentityStore()
        self.users = InMemoryUserRepository(store)
        self.sessions = InMemorySessionRepository()
        self.tokens = InMemoryApiTokenRepository()
        self.audit = InMemoryAuditLog()
        self.settings = InMemoryInstanceSettingsRepository()
        self.lifecycle = InMemoryUserLifecycle(store)

    async def add_user(self, email: str = "anna@example.org", *, admin: bool = False) -> User:
        user = User(
            id=f"u_{await self.users.count()}",
            email=email,
            email_normalized=normalize_email(email),
            name="Анна Петрова",
            status=UserStatus.active,
            created_at=NOW,
            email_verified=True,
            is_instance_admin=admin,
        )
        await self.users.add(user)
        await self.settings.set(KEY_SETUP_COMPLETED, True, source="test")
        return user

    async def add_session(self, user: User, secret: str) -> None:
        await self.sessions.add(
            Session(
                id_hash=hash_token(secret),
                user_id=user.id,
                csrf_token=f"csrf-{secret}",
                created_at=NOW,
                last_seen_at=NOW,
                expires_at=NOW + timedelta(days=7),
            )
        )

    async def add_token(self, user: User, secret: str, **fields: Any) -> ApiToken:
        token = ApiToken(
            **{
                "id": f"pat_{secret}",
                "user_id": user.id,
                "name": "t",
                "token_hash": hash_token(secret),
                "prefix": secret[:11],
                "scopes": frozenset({TokenScope.api}),
                "created_at": NOW,
                **fields,
            }
        )
        await self.tokens.add(token)
        return token


class _Provider(Provider):
    scope = Scope.APP

    def __init__(self, world: _World) -> None:
        super().__init__()
        self._w = world
        self._service = SessionService(world.sessions, world.users)

    @provide
    def resolver(self) -> IActorResolver:
        w = self._w
        return ChainActorResolver([SessionCookieResolver(self._service), BearerActorResolver(w.tokens, w.users)])

    @provide
    def export_data(self) -> ExportMyDataUC:
        return ExportMyDataUC(self._w.lifecycle, self._w.audit)

    @provide
    def list_sessions(self) -> ListSessionsUC:
        return ListSessionsUC(self._w.sessions)

    @provide
    def list_tokens(self) -> ListApiTokensUC:
        return ListApiTokensUC(self._w.tokens)

    @provide
    def create_token(self) -> CreateApiTokenUC:
        return CreateApiTokenUC(self._w.tokens, self._w.audit, _Uow())

    @provide
    def update_token(self) -> UpdateApiTokenScopesUC:
        return UpdateApiTokenScopesUC(self._w.tokens, self._w.audit, _Uow())

    @provide
    def revoke_token(self) -> RevokeApiTokenUC:
        return RevokeApiTokenUC(self._w.tokens, self._w.audit, _Uow())


@pytest_asyncio.fixture
async def env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, _World]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(route_scopes, "ROUTE_SCOPES", {**ROUTE_SCOPES, ("GET", "/whoami"): RouteScope.authenticated})
    world = _World()
    probe = APIRouter(prefix="/api/v1", dependencies=[Depends(project_access_guard)])

    @probe.get("/whoami")
    async def whoami() -> dict[str, str | None]:
        actor = current_actor()
        return {"id": actor.id if actor else None}

    app = FastAPI()
    app.include_router(api_router)
    app.include_router(probe)
    install_exception_handlers(app)
    container = make_async_container(_Provider(world), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, world
    await container.close()


def _cookie(secret: str) -> dict[str, str]:
    return {"Cookie": f"{SESSION_COOKIE}={secret}"}


def _bearer(secret: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


async def _issue(client: AsyncClient, world: _World, **body: Any) -> dict[str, Any]:
    user = await world.add_user()
    await world.add_session(user, "mine")
    response = await client.post("/api/v1/account/tokens", json={**CREATE, **body}, headers=_cookie("mine"))
    assert response.status_code == 201
    return response.json()


async def test_create_matches_the_contract_and_shows_the_secret_once(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world)

    expected = json.loads((_FIXTURES / "CreateApiTokenResponse" / "cli.json").read_text(encoding="utf-8"))
    assert set(created) == set(expected)
    assert set(created["item"]) == set(expected["item"])
    secret = created["token"]
    assert secret.startswith("hsd_pat_")
    assert len(secret) == 40
    assert created["item"]["prefix"] == secret[:11]
    assert created["item"]["scopes"] == ["api", "git:read"]
    stored = await world.tokens.list_for_user("u_0")
    assert stored[0].token_hash == hash_token(secret)
    listing = await client.get("/api/v1/account/tokens", headers=_cookie("mine"))
    assert secret not in listing.text
    assert listing.json()[0]["prefix"] == secret[:11]
    assert "token" not in listing.json()[0]


async def test_create_response_is_not_cacheable_and_is_audited_without_the_secret(
    env: tuple[AsyncClient, _World],
) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")

    response = await client.post("/api/v1/account/tokens", json=CREATE, headers=_cookie("mine"))

    assert response.headers["cache-control"] == "no-store"
    events = [e for e in await world.audit.list(limit=50) if e.action == "pat.create"]
    assert len(events) == 1
    assert response.json()["token"] not in json.dumps(events[0].details)


@pytest.mark.parametrize(
    "body",
    [
        {**CREATE, "name": ""},
        {**CREATE, "name": "x" * 81},
        {**CREATE, "scopes": []},
        {**CREATE, "scopes": ["admin"]},
        {**CREATE, "expires_in_days": 0},
        {**CREATE, "expires_in_days": 366},
    ],
)
async def test_create_validates_the_request(env: tuple[AsyncClient, _World], body: dict[str, Any]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")

    response = await client.post("/api/v1/account/tokens", json=body, headers=_cookie("mine"))

    assert response.status_code == 422


async def test_token_without_expiry_never_expires(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world, expires_in_days=None)

    assert created["item"]["expires_at"] is None


async def test_bearer_token_authenticates_api_and_records_use(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world)

    response = await client.get("/api/v1/whoami", headers=_bearer(created["token"]))

    assert response.status_code == 200
    token = (await world.tokens.list_for_user("u_0"))[0]
    assert token.last_used_at is not None


async def test_unknown_and_malformed_bearer_is_401(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()

    for secret in ("hsd_pat_" + "a" * 32, "garbage"):
        response = await client.get("/api/v1/whoami", headers=_bearer(secret))
        assert response.status_code == 401
        assert response.json()["code"] == "auth_required"


async def test_expired_token_is_401(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    secret = "hsd_pat_" + "e" * 32
    await world.add_token(user, secret, expires_at=NOW - timedelta(seconds=1))

    response = await client.get("/api/v1/whoami", headers=_bearer(secret))

    assert response.status_code == 401


async def test_revoked_token_is_401_at_once(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world)
    token_id = created["item"]["id"]

    assert (await client.get("/api/v1/whoami", headers=_bearer(created["token"]))).status_code == 200
    revoked = await client.delete(
        f"/api/v1/account/tokens/{token_id}", headers={**_cookie("mine"), "X-CSRF-Token": "csrf-mine"}
    )
    assert revoked.status_code == 204
    assert (await client.get("/api/v1/whoami", headers=_bearer(created["token"]))).status_code == 401
    assert [e.action for e in await world.audit.list(limit=50)] == ["pat.revoke", "pat.create"]


async def test_token_of_a_disabled_user_is_401(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world)
    user = await world.users.get("u_0")
    assert user is not None
    await world.users.update(type(user)(**{**user.__dict__, "status": UserStatus.disabled}))

    assert (await client.get("/api/v1/whoami", headers=_bearer(created["token"]))).status_code == 401


async def test_git_only_token_cannot_call_the_api(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    secret = "hsd_pat_" + "g" * 32
    await world.add_token(user, secret, scopes=frozenset({TokenScope.git_read}))

    response = await client.get("/api/v1/whoami", headers=_bearer(secret))

    assert response.status_code == 403


async def test_token_cannot_manage_tokens(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world)
    headers = _bearer(created["token"])
    token_id = created["item"]["id"]

    assert (await client.get("/api/v1/account/tokens", headers=headers)).status_code == 403
    assert (await client.post("/api/v1/account/tokens", json=CREATE, headers=headers)).status_code == 403
    assert (await client.delete(f"/api/v1/account/tokens/{token_id}", headers=headers)).status_code == 403
    assert len(await world.tokens.list_for_user("u_0")) == 1


async def test_token_routes_require_a_login(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    await world.add_user()

    assert (await client.get("/api/v1/account/tokens")).status_code == 401


async def test_tokens_do_not_leak_between_users(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    anna = await world.add_user()
    boris = await world.add_user("boris@example.org")
    await world.add_session(anna, "anna")
    await world.add_session(boris, "boris")
    created = (await client.post("/api/v1/account/tokens", json=CREATE, headers=_cookie("anna"))).json()

    assert (await client.get("/api/v1/account/tokens", headers=_cookie("boris"))).json() == []
    foreign = await client.delete(
        f"/api/v1/account/tokens/{created['item']['id']}", headers={**_cookie("boris"), "X-CSRF-Token": "csrf-boris"}
    )
    assert foreign.status_code == 404
    assert len(await world.tokens.list_for_user(anna.id)) == 1


async def test_export_is_an_uncached_attachment_with_own_data_and_audited(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")

    response = await client.get("/api/v1/account/export", headers=_cookie("mine"))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert "attachment" in response.headers["content-disposition"]
    assert response.json()["profile"]["id"] == user.id
    assert [e.actor_id for e in await world.audit.list(limit=50) if e.action == "account.data_exported"] == [user.id]


async def test_export_by_token_or_anonymous_is_refused(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_token(user, "hsd_pat_exporttoken0000000000000000000")

    by_token = await client.get("/api/v1/account/export", headers=_bearer("hsd_pat_exporttoken0000000000000000000"))
    anonymous = await client.get("/api/v1/account/export")

    assert (by_token.status_code, anonymous.status_code) == (403, 401)


# Смена прав существующего токена (PATCH /account/tokens/{id}): значение то же, права новые со следующего запроса.


async def _patch(client: AsyncClient, token_id: str, scopes: list[str], headers: dict[str, str]) -> Any:
    return await client.patch(f"/api/v1/account/tokens/{token_id}", json={"scopes": scopes}, headers=headers)


async def test_owner_changes_scopes_and_the_next_request_uses_them(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world, scopes=["git:read"])
    token_id, secret = created["item"]["id"], created["token"]
    assert (await client.get("/api/v1/whoami", headers=_bearer(secret))).status_code == 403

    added = await _patch(client, token_id, ["git:read", "api", "mcp"], _cookie("mine"))

    assert added.status_code == 200, added.text
    assert added.headers["cache-control"] == "no-store"
    assert added.json()["scopes"] == ["api", "git:read", "mcp"]
    assert added.json()["prefix"] == created["item"]["prefix"]
    assert secret not in added.text
    assert (await client.get("/api/v1/whoami", headers=_bearer(secret))).status_code == 200

    removed = await _patch(client, token_id, ["mcp"], _cookie("mine"))

    assert removed.json()["scopes"] == ["mcp"]
    assert (await client.get("/api/v1/whoami", headers=_bearer(secret))).status_code == 403
    listing = (await client.get("/api/v1/account/tokens", headers=_cookie("mine"))).json()
    assert listing[0]["scopes"] == ["mcp"]
    events = [e for e in await world.audit.list(limit=50) if e.action == "pat.scopes_update"]
    assert [(e.target, e.details["added"], e.details["removed"]) for e in reversed(events)] == [
        (token_id, ["api", "mcp"], []),
        (token_id, [], ["api", "git:read"]),
    ]
    assert all(secret not in json.dumps(e.details) for e in events)


async def test_same_scopes_change_nothing_and_are_not_audited(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world)

    response = await _patch(client, created["item"]["id"], ["git:read", "api"], _cookie("mine"))

    assert response.status_code == 200
    assert response.json()["scopes"] == ["api", "git:read"]
    assert not [e for e in await world.audit.list(limit=50) if e.action == "pat.scopes_update"]


async def test_token_cannot_change_scopes_of_itself_or_another_token(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world, scopes=["api"])
    other = await client.post("/api/v1/account/tokens", json=CREATE, headers=_cookie("mine"))
    headers = _bearer(created["token"])

    own = await _patch(client, created["item"]["id"], ["api", "mcp", "packs"], headers)
    foreign = await _patch(client, other.json()["item"]["id"], ["api", "git:write"], headers)

    assert (own.status_code, foreign.status_code) == (403, 403)
    assert [t.scopes for t in await world.tokens.list_for_user("u_0")] == [
        frozenset({TokenScope.api}),
        frozenset({TokenScope.api, TokenScope.git_read}),
    ]


async def test_scope_change_needs_a_login(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world)

    response = await _patch(client, created["item"]["id"], ["api"], {})

    assert response.status_code == 401


async def test_another_user_cannot_change_scopes(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world, scopes=["api"])
    boris = await world.add_user("boris@example.org")
    await world.add_session(boris, "boris")

    response = await _patch(client, created["item"]["id"], ["api", "mcp"], _cookie("boris"))

    assert response.status_code == 404
    assert [t.scopes for t in await world.tokens.list_for_user("u_0")] == [frozenset({TokenScope.api})]


async def test_revoked_token_cannot_be_changed(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world)
    token_id = created["item"]["id"]
    await client.delete(f"/api/v1/account/tokens/{token_id}", headers={**_cookie("mine"), "X-CSRF-Token": "csrf-mine"})

    response = await _patch(client, token_id, ["api", "mcp"], _cookie("mine"))

    assert response.status_code == 404
    assert await world.tokens.list_for_user("u_0") == []


async def test_expired_token_cannot_be_changed(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")
    token = await world.add_token(user, "hsd_pat_" + "x" * 32, expires_at=NOW - timedelta(seconds=1))

    response = await _patch(client, token.id, ["api", "mcp"], _cookie("mine"))

    assert response.status_code == 409
    assert response.json()["code"] == "api_token_expired"
    assert (await world.tokens.list_for_user(user.id))[0].scopes == frozenset({TokenScope.api})


async def test_admin_only_scope_is_refused_to_a_non_admin(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    created = await _issue(client, world, scopes=["mcp"])

    changed = await _patch(client, created["item"]["id"], ["mcp", "mcp:admin"], _cookie("mine"))
    issued = await client.post(
        "/api/v1/account/tokens", json={**CREATE, "scopes": ["mcp", "mcp:admin"]}, headers=_cookie("mine")
    )

    assert (changed.status_code, issued.status_code) == (403, 403)
    assert changed.json()["code"] == issued.json()["code"] == "token_scope_not_allowed"
    assert [t.scopes for t in await world.tokens.list_for_user("u_0")] == [frozenset({TokenScope.mcp})]


async def test_admin_may_add_the_admin_scope(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    admin = await world.add_user(admin=True)
    await world.add_session(admin, "root")
    token = await world.add_token(admin, "hsd_pat_" + "r" * 32, scopes=frozenset({TokenScope.mcp}))

    response = await _patch(client, token.id, ["mcp", "mcp:admin"], _cookie("root"))

    assert response.status_code == 200, response.text
    assert response.json()["scopes"] == ["mcp", "mcp:admin"]


async def test_removing_a_scope_that_is_no_longer_allowed_is_fine(env: tuple[AsyncClient, _World]) -> None:
    """Бывший админ: `mcp:admin` у токена остался; его можно убрать и можно оставить, добавляя другое право."""
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")
    token = await world.add_token(user, "hsd_pat_" + "f" * 32, scopes=frozenset({TokenScope.mcp, TokenScope.mcp_admin}))

    kept = await _patch(client, token.id, ["mcp", "mcp:admin", "packs"], _cookie("mine"))
    dropped = await _patch(client, token.id, ["mcp"], _cookie("mine"))

    assert (kept.status_code, dropped.status_code) == (200, 200)
    assert dropped.json()["scopes"] == ["mcp"]


async def test_device_token_stays_a_git_token(env: tuple[AsyncClient, _World]) -> None:
    client, world = env
    user = await world.add_user()
    await world.add_session(user, "mine")
    token = await world.add_token(
        user, "hsd_pat_" + "d" * 32, scopes=frozenset({TokenScope.git_read}), origin=ApiTokenOrigin.device
    )

    refused = await _patch(client, token.id, ["git:read", "api"], _cookie("mine"))
    allowed = await _patch(client, token.id, ["git:read", "git:write"], _cookie("mine"))

    assert refused.status_code == 403
    assert refused.json()["code"] == "token_scope_not_allowed"
    assert allowed.json()["scopes"] == ["git:read", "git:write"]


@pytest.mark.parametrize("scopes", [[], ["admin"], ["api"] * 8])
async def test_scope_change_validates_the_request(env: tuple[AsyncClient, _World], scopes: list[str]) -> None:
    client, world = env
    created = await _issue(client, world)

    response = await _patch(client, created["item"]["id"], scopes, _cookie("mine"))

    assert response.status_code == 422
