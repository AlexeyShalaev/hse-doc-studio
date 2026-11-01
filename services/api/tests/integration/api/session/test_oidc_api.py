"""Вход через OIDC по HTTP: переход к провайдеру, возврат, cookie, безопасный next, ошибки на странице /auth/error."""

from __future__ import annotations

from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.auth_cookie import OIDC_STATE_COOKIE, SESSION_COOKIE
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.v1 import api_router
from hse_doc_studio.core.identity.entities import UserIdentity
from hse_doc_studio.core.identity.oidc import OidcProviderConfig
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.identity.oidc.client import OidcClient
from hse_doc_studio.infra.identity.oidc.state import HmacOidcStateCodec
from hse_doc_studio.infra.identity.resolvers import ChainActorResolver, SessionCookieResolver
from hse_doc_studio.use_cases.identity.bootstrap import BootstrapUC
from hse_doc_studio.use_cases.identity.oidc_identities import ListOidcIdentitiesUC, UnlinkOidcIdentityUC
from hse_doc_studio.use_cases.identity.oidc_login import CompleteOidcLoginUC, StartOidcLoginUC
from hse_doc_studio.use_cases.server_setup.state import SetupStateService
from httpx import ASGITransport, AsyncClient

from tests.fakes.auth import empty_bearer_resolver
from tests.fixtures.fake_oidc import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeIdp
from tests.unit.use_cases.identity.conftest import World
from tests.unit.use_cases.identity.test_oidc_login import _Catalog

PROVIDER = OidcProviderConfig("sso", "SSO", ISSUER, CLIENT_ID, CLIENT_SECRET)
START = "/api/v1/auth/oidc/sso/start"
CALLBACK = "/api/v1/auth/oidc/sso/callback"


class _Stack(Provider):
    scope = Scope.APP

    def __init__(self, world: World, idp: FakeIdp) -> None:
        super().__init__()
        self._w = world
        catalog = _Catalog(PROVIDER)
        client = OidcClient(http=idp.http_client())
        codec = HmacOidcStateCodec([b"k" * 32])
        self._start = StartOidcLoginUC(catalog, client, codec, world.clock)
        self._complete = CompleteOidcLoginUC(
            catalog,
            client,
            codec,
            world.users,
            world.sessions,
            world.audit,
            world.uow,
            world.policy,
            world.clock,
            auth_settings=world.settings_service(),
        )

    @provide
    def resolver(self) -> IActorResolver:
        return ChainActorResolver([SessionCookieResolver(self._w.service()), empty_bearer_resolver()])

    @provide
    def start(self) -> StartOidcLoginUC:
        return self._start

    @provide
    def complete(self) -> CompleteOidcLoginUC:
        return self._complete

    @provide
    def list_identities(self) -> ListOidcIdentitiesUC:
        return ListOidcIdentitiesUC(self._w.users, _Catalog(PROVIDER))

    @provide
    def unlink(self) -> UnlinkOidcIdentityUC:
        w = self._w
        return UnlinkOidcIdentityUC(w.users, w.creds, w.settings_service(), w.audit, w.uow)

    @provide
    def bootstrap(self) -> BootstrapUC:
        w = self._w
        return BootstrapUC(
            SetupStateService(w.settings),
            w.settings_service(),
            w.service(),
            oidc_providers=_Catalog(PROVIDER).list_enabled,
        )


@pytest_asyncio.fixture
async def env(world: World, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, World, FakeIdp]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    monkeypatch.setattr(settings.auth, "public_url", "http://test")
    user = await world.add_user()
    await world.users.add_identity(UserIdentity(user.id, "sso", "idp-user-1", "ann@example.org", True))
    idp = FakeIdp()
    app = FastAPI()
    app.include_router(api_router)
    install_exception_handlers(app)
    container = make_async_container(_Stack(world, idp), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, world, idp
    await container.close()


async def _start(client: AsyncClient, idp: FakeIdp, next_path: str | None = "/projects", **overrides: object):  # type: ignore[no-untyped-def]
    response = await client.get(START, params={"next": next_path} if next_path is not None else None)
    assert response.status_code == 302
    code, state = idp.authorize(response.headers["location"], **overrides)
    return response, code, state


async def test_start_redirects_to_the_provider_and_sets_the_state_cookie(
    env: tuple[AsyncClient, World, FakeIdp],
) -> None:
    client, _, idp = env

    response, _, state = await _start(client, idp)

    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["redirect_uri"] == [f"http://test{CALLBACK}"]
    assert query["state"] == [state]
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{OIDC_STATE_COOKIE}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert response.headers["cache-control"] == "no-store"


async def test_full_login_sets_the_session_cookie_and_returns_to_next(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, world, idp = env
    _, code, state = await _start(client, idp)

    response = await client.get(CALLBACK, params={"code": code, "state": state})

    assert response.status_code == 302
    assert response.headers["location"] == "/projects"
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(c for c in cookies if c.startswith(f"{SESSION_COOKIE}="))
    assert "HttpOnly" in session_cookie
    assert any(c.startswith(f"{OIDC_STATE_COOKIE}=") and "Max-Age=0" in c for c in cookies)
    secret = session_cookie.split("=", 1)[1].split(";", 1)[0]
    assert await world.service().resolve(secret) is not None
    bootstrap = await client.get("/api/v1/session/bootstrap")
    assert bootstrap.json()["user"]["email"] == "ann@example.org"
    assert bootstrap.json()["auth"]["oidc_providers"] == [{"id": "sso", "label": "SSO"}]


@pytest.mark.parametrize(
    "next_path", ["https://evil.test/", "//evil.test", "/\\evil.test", "javascript:alert(1)", "evil", ""]
)
async def test_open_redirect_through_next_is_neutralised(
    env: tuple[AsyncClient, World, FakeIdp], next_path: str
) -> None:
    client, _, idp = env
    _, code, state = await _start(client, idp, next_path)

    response = await client.get(CALLBACK, params={"code": code, "state": state})

    assert response.headers["location"] == "/"


async def test_bad_state_ends_on_the_error_page_without_session(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, world, idp = env
    _, code, _ = await _start(client, idp)

    response = await client.get(CALLBACK, params={"code": code, "state": "forged"})

    assert response.headers["location"] == "/auth/error?code=oidc_state_invalid"
    assert SESSION_COOKIE not in response.headers.get("set-cookie", "")
    assert not world.sessions._items  # noqa: SLF001


async def test_callback_without_start_cookie_is_refused(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, _, idp = env
    _, code, state = await _start(client, idp)
    client.cookies.clear()

    response = await client.get(CALLBACK, params={"code": code, "state": state})

    assert response.headers["location"] == "/auth/error?code=oidc_state_invalid"


async def test_bad_nonce_ends_on_the_error_page(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, _, idp = env
    _, code, state = await _start(client, idp, nonce="replayed")

    response = await client.get(CALLBACK, params={"code": code, "state": state})

    assert response.headers["location"] == "/auth/error?code=oidc_token_invalid"


async def test_provider_error_and_unlinked_account_codes(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, _, idp = env
    _, _, state = await _start(client, idp)
    denied = await client.get(CALLBACK, params={"error": "access_denied", "state": state})
    _, code, state = await _start(client, idp, sub="stranger", email="new@example.org")
    unlinked = await client.get(CALLBACK, params={"code": code, "state": state})

    assert denied.headers["location"] == "/auth/error?code=oidc_provider_denied"
    assert unlinked.headers["location"] == "/auth/error?code=oidc_not_linked"


async def test_unknown_provider_and_unreachable_provider(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, _, idp = env
    unknown = await client.get("/api/v1/auth/oidc/nope/start")
    idp.discovery_status = 503
    down = await client.get(START)

    assert unknown.headers["location"] == "/auth/error?code=oidc_provider_unknown"
    assert down.headers["location"] == "/auth/error?code=oidc_discovery_failed"


async def test_routes_are_absent_in_local_mode(
    env: tuple[AsyncClient, World, FakeIdp], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _ = env
    monkeypatch.setattr(settings, "mode", StudioMode.local)

    assert (await client.get(START)).status_code == 404
    assert (await client.get(CALLBACK)).status_code == 404


async def test_verified_email_of_an_unlinked_identity_links_and_signs_in(
    env: tuple[AsyncClient, World, FakeIdp],
) -> None:
    client, world, idp = env
    await world.add_user("bob@example.org", user_id="u2")
    _, code, state = await _start(client, idp, sub="bobs-sub", email="bob@example.org", email_verified=True)

    response = await client.get(CALLBACK, params={"code": code, "state": state})

    assert response.headers["location"] == "/projects"
    assert SESSION_COOKIE in response.headers["set-cookie"]
    assert [i.subject for i in await world.users.list_identities("u2")] == ["bobs-sub"]


async def test_unverified_email_does_not_take_over_the_account(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, world, idp = env
    _, code, state = await _start(client, idp, sub="evil", email="ann@example.org", email_verified=False)

    response = await client.get(CALLBACK, params={"code": code, "state": state})

    assert response.headers["location"] == "/auth/error?code=oidc_email_unverified"
    assert SESSION_COOKIE not in response.headers.get("set-cookie", "")
    assert [i.subject for i in await world.users.list_identities("u1")] == ["idp-user-1"]


async def test_link_from_profile_and_unlink(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, world, idp = env
    await world.users.delete_identity("u1", "sso")
    login = await world.login_uc().execute("ann@example.org", "correct horse battery")

    anonymous = await client.get("/api/v1/account/identities/sso/link")
    client.cookies.set(SESSION_COOKIE, login.secret)
    started = await client.get("/api/v1/account/identities/sso/link", params={"next": "/settings"})
    code, state = idp.authorize(started.headers["location"], sub="linked-sub", email="other@else.org")
    done = await client.get(CALLBACK, params={"code": code, "state": state})
    listing = await client.get("/api/v1/account/identities")
    unlinked = await client.delete("/api/v1/account/identities/sso")

    assert anonymous.status_code == 401
    assert done.headers["location"] == "/settings"
    assert "set-cookie" in done.headers
    assert SESSION_COOKIE not in "".join(done.headers.get_list("set-cookie"))
    assert [i["provider"] for i in listing.json()] == ["sso"]
    assert unlinked.status_code == 204
    assert await world.users.list_identities("u1") == []


async def test_last_login_method_cannot_be_unlinked(env: tuple[AsyncClient, World, FakeIdp]) -> None:
    client, world, _ = env
    login = await world.login_uc().execute("ann@example.org", "correct horse battery")
    world.store.hashes.clear()

    response = await client.delete(
        "/api/v1/account/identities/sso", headers={"Cookie": f"{SESSION_COOKIE}={login.secret}"}
    )

    assert (response.status_code, response.json()["code"]) == (409, "last_login_method")
