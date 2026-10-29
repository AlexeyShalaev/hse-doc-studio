"""Вход через OIDC: старт, возврат, состояние в cookie, безопасный next. Провайдер фейковый."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from hse_doc_studio.core.identity.entities import UserIdentity, UserStatus
from hse_doc_studio.core.identity.oidc import (
    OidcErrorCode,
    OidcLoginError,
    OidcLoginState,
    OidcProviderConfig,
    safe_next,
)
from hse_doc_studio.infra.identity.oidc.client import OidcClient
from hse_doc_studio.infra.identity.oidc.state import HmacOidcStateCodec
from hse_doc_studio.use_cases.identity.oidc_login import CompleteOidcLoginUC, StartOidcLoginUC

from tests.fixtures.fake_oidc import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeIdp
from tests.unit.use_cases.identity.conftest import T0, World

REDIRECT = "https://studio.test/api/v1/auth/oidc/sso/callback"
PROVIDER = OidcProviderConfig("sso", "SSO", ISSUER, CLIENT_ID, CLIENT_SECRET)


class _Catalog:
    def __init__(self, *providers: OidcProviderConfig) -> None:
        self._items = {p.id: p for p in providers}

    async def get(self, provider_id: str) -> OidcProviderConfig | None:
        return self._items.get(provider_id)

    async def list_enabled(self) -> list[tuple[str, str]]:
        return [(p.id, p.label) for p in self._items.values()]


class _Flow:
    def __init__(self, world: World) -> None:
        self.world = world
        self.idp = FakeIdp()
        self.codec = HmacOidcStateCodec([b"k" * 32])
        client = OidcClient(http=self.idp.http_client())
        catalog = _Catalog(PROVIDER)
        self.start = StartOidcLoginUC(catalog, client, self.codec, world.clock)
        self.complete = CompleteOidcLoginUC(
            catalog, client, self.codec, world.users, world.sessions, world.audit, world.uow, world.policy, world.clock
        )

    async def begin(self, **overrides: object) -> tuple[str, str, str]:
        """Возвращает (cookie состояния, state в адресе возврата, код)."""
        started = await self.start.execute("sso", redirect_uri=REDIRECT, next_path="/projects")
        code, state = self.idp.authorize(started.authorize_url, **overrides)
        return started.sealed_state, state, code

    async def finish(self, sealed: str | None, state: str | None, code: str | None, *, error: str | None = None):  # type: ignore[no-untyped-def]
        return await self.complete.execute(
            "sso", sealed_state=sealed, state=state, code=code, error=error, ip="1.2.3.4", user_agent="UA"
        )


@pytest.fixture
async def flow(world: World) -> _Flow:
    user = await world.add_user()
    await world.users.add_identity(UserIdentity(user.id, "sso", "idp-user-1", "ann@example.org", True))
    return _Flow(world)


async def test_start_builds_authorize_url_with_state_and_pkce(flow: _Flow) -> None:
    started = await flow.start.execute("sso", redirect_uri=REDIRECT, next_path="/projects")

    query = parse_qs(urlsplit(started.authorize_url).query)
    saved = flow.codec.open(started.sealed_state)
    assert saved is not None
    assert query["state"] == [saved.state]
    assert query["nonce"] == [saved.nonce]
    assert query["scope"] == ["openid email profile"]
    assert saved.code_verifier not in started.authorize_url
    assert saved.next_path == "/projects"


async def test_unknown_provider_fails_to_start(flow: _Flow) -> None:
    with pytest.raises(OidcLoginError) as caught:
        await flow.start.execute("nope", redirect_uri=REDIRECT, next_path=None)

    assert caught.value.code is OidcErrorCode.provider_unknown


async def test_success_creates_a_session_for_the_linked_user(flow: _Flow) -> None:
    sealed, state, code = await flow.begin()

    result = await flow.finish(sealed, state, code)

    assert result.user.id == "u1"
    assert result.next_path == "/projects"
    assert result.session.user_id == "u1"
    assert result.user.last_login_at == T0
    logins = [e for e in flow.world.audit._entries if e.action == "auth.login"]  # noqa: SLF001
    assert logins[-1].details["method"] == "oidc:sso"


async def test_state_mismatch_is_rejected(flow: _Flow) -> None:
    sealed, _, code = await flow.begin()

    with pytest.raises(OidcLoginError) as caught:
        await flow.finish(sealed, "forged-state", code)

    assert caught.value.code is OidcErrorCode.state_invalid


async def test_missing_cookie_is_rejected_even_with_provider_error(flow: _Flow) -> None:
    _, state, code = await flow.begin()

    for error in (None, "access_denied"):
        with pytest.raises(OidcLoginError) as caught:
            await flow.finish(None, state, code, error=error)
        assert caught.value.code is OidcErrorCode.state_invalid


async def test_tampered_cookie_is_rejected(flow: _Flow) -> None:
    sealed, state, code = await flow.begin()
    body, _, signature = sealed.partition(".")

    for broken in (f"{body}x.{signature}", f"{body}.{signature[:-2]}AA", "garbage", body):
        with pytest.raises(OidcLoginError) as caught:
            await flow.finish(broken, state, code)
        assert caught.value.code is OidcErrorCode.state_invalid


async def test_cookie_signed_with_another_key_is_rejected(flow: _Flow) -> None:
    sealed, state, code = await flow.begin()
    other = HmacOidcStateCodec([b"z" * 32])
    forged = other.seal(flow.codec.open(sealed))  # type: ignore[arg-type]

    with pytest.raises(OidcLoginError) as caught:
        await flow.finish(forged, state, code)

    assert caught.value.code is OidcErrorCode.state_invalid


async def test_cookie_of_another_provider_is_rejected(flow: _Flow) -> None:
    sealed, state, code = await flow.begin()
    saved = flow.codec.open(sealed)
    assert saved is not None
    swapped = flow.codec.seal(replace(saved, provider_id="other"))

    with pytest.raises(OidcLoginError) as caught:
        await flow.finish(swapped, state, code)

    assert caught.value.code is OidcErrorCode.state_invalid


async def test_expired_state_is_rejected(flow: _Flow) -> None:
    sealed, state, code = await flow.begin()
    flow.world.clock.advance(minutes=11)

    with pytest.raises(OidcLoginError) as caught:
        await flow.finish(sealed, state, code)

    assert caught.value.code is OidcErrorCode.state_expired


async def test_provider_error_is_reported(flow: _Flow) -> None:
    sealed, state, _ = await flow.begin()

    with pytest.raises(OidcLoginError) as caught:
        await flow.finish(sealed, state, None, error="access_denied")

    assert caught.value.code is OidcErrorCode.provider_denied


@pytest.mark.parametrize(
    "override", [{"nonce": "replayed"}, {"aud": "other"}, {"iss": "https://evil.test"}, {"exp": 5}]
)
async def test_bad_id_token_does_not_sign_in(flow: _Flow, override: dict[str, object]) -> None:
    sealed, state, code = await flow.begin(**override)

    with pytest.raises(OidcLoginError) as caught:
        await flow.finish(sealed, state, code)

    assert caught.value.code is OidcErrorCode.token_invalid
    assert not flow.world.sessions._items  # noqa: SLF001


async def test_unlinked_identity_does_not_sign_in_even_with_matching_email(flow: _Flow) -> None:
    sealed, state, code = await flow.begin(sub="stranger", email="ann@example.org", email_verified=True)

    with pytest.raises(OidcLoginError) as caught:
        await flow.finish(sealed, state, code)

    assert caught.value.code is OidcErrorCode.not_linked
    assert len(await flow.world.users.list_identities("u1")) == 1


@pytest.mark.parametrize("status", [UserStatus.disabled, UserStatus.pending_approval, UserStatus.pending_verification])
async def test_inactive_account_does_not_sign_in(flow: _Flow, status: UserStatus) -> None:
    user = await flow.world.users.get("u1")
    assert user is not None
    await flow.world.users.update(replace(user, status=status))
    sealed, state, code = await flow.begin()

    with pytest.raises(OidcLoginError) as caught:
        await flow.finish(sealed, state, code)

    assert caught.value.code is OidcErrorCode.account_denied


async def test_previous_session_is_closed_on_sign_in(flow: _Flow) -> None:
    first = await flow.world.login_uc().execute("ann@example.org", "correct horse battery")
    sealed, state, code = await flow.begin()

    result = await flow.complete.execute(
        "sso", sealed_state=sealed, state=state, code=code, error=None, previous_secret=first.secret
    )

    assert result.secret != first.secret
    assert await flow.world.service().resolve(first.secret) is None
    assert await flow.world.service().resolve(result.secret) is not None


def test_state_codec_roundtrip_and_key_rotation() -> None:
    state = OidcLoginState("sso", "s", "n", "v", REDIRECT, "/x", T0 + timedelta(minutes=10))
    old = HmacOidcStateCodec([b"a" * 32])
    rotated = HmacOidcStateCodec([b"b" * 32, b"a" * 32])

    assert old.open(old.seal(state)) == state
    assert rotated.open(old.seal(state)) == state
    assert old.open(rotated.seal(state)) is None


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.test/",
        "//evil.test/path",
        "/\\evil.test",
        "\\\\evil.test",
        "javascript:alert(1)",
        "evil.test",
        "/ok\r\nSet-Cookie: a=b",
        "/a b",
        "/\tevil",
        "",
        None,
        "/" + "a" * 3000,
    ],
)
def test_safe_next_rejects_foreign_targets(value: str | None) -> None:
    assert safe_next(value) == "/"


@pytest.mark.parametrize("value", ["/", "/projects/abc?tab=files", "/a/b#frag", "/%2Fevil"])
def test_safe_next_keeps_local_paths(value: str) -> None:
    assert safe_next(value) == value
