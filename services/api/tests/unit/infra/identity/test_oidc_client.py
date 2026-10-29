"""Клиент OIDC против фейкового провайдера: discovery, обмен кода, проверка ID-токена, ротация ключей."""

from __future__ import annotations

import base64

import pytest
from hse_doc_studio.core.identity.oidc import (
    OidcAuthorizeRequest,
    OidcClaims,
    OidcErrorCode,
    OidcLoginError,
    OidcProviderConfig,
)
from hse_doc_studio.infra.identity.oidc.client import OidcClient
from hse_doc_studio.use_cases.identity.oidc_login import pkce_challenge

from tests.fixtures.fake_oidc import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeIdp, IssuedCode

REDIRECT = "https://studio.test/api/v1/auth/oidc/sso/callback"
VERIFIER = "v" * 64
CHALLENGE = pkce_challenge(VERIFIER)


def _provider(**kw: object) -> OidcProviderConfig:
    base = {"id": "sso", "label": "SSO", "issuer": ISSUER, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
    return OidcProviderConfig(**{**base, **kw})  # type: ignore[arg-type]


@pytest.fixture
def idp() -> FakeIdp:
    return FakeIdp()


def _client(idp: FakeIdp, **kw: float) -> OidcClient:
    return OidcClient(http=idp.http_client(), **kw)


async def _login(client: OidcClient, idp: FakeIdp, **overrides: object) -> OidcClaims:
    request = OidcAuthorizeRequest(_provider(), REDIRECT, "state-1", "nonce-1", CHALLENGE)
    code, _ = idp.authorize(await client.authorize_url(request), **overrides)
    return await client.exchange(_provider(), code=code, code_verifier=VERIFIER, redirect_uri=REDIRECT, nonce="nonce-1")


async def test_success_returns_verified_claims(idp: FakeIdp) -> None:
    claims = await _login(_client(idp), idp)

    assert claims == OidcClaims("sso", "idp-user-1", "ann@example.org", True, "Ann")


async def test_authorize_url_carries_pkce_state_and_nonce(idp: FakeIdp) -> None:
    url = await _client(idp).authorize_url(OidcAuthorizeRequest(_provider(), REDIRECT, "st", "nn", CHALLENGE))

    assert url.startswith(f"{ISSUER}/protocol/openid-connect/auth?")
    for part in (
        "response_type=code",
        "state=st",
        "nonce=nn",
        "code_challenge_method=S256",
        f"code_challenge={CHALLENGE}",
    ):
        assert part in url


async def test_discovery_and_keys_are_cached(idp: FakeIdp) -> None:
    client = _client(idp)

    await _login(client, idp)
    await _login(client, idp)

    assert idp.count("openid-configuration") == 1
    assert idp.count("/certs") == 1


async def test_client_secret_basic_by_default_post_when_only_post_supported(idp: FakeIdp) -> None:
    idp.auth_methods = ["client_secret_post"]
    await _login(_client(idp), idp)
    token_request = next(r for r in idp.requests if r.url.path.endswith("/token"))

    assert "authorization" not in token_request.headers
    assert f"client_id={CLIENT_ID}" in token_request.content.decode()


@pytest.mark.parametrize(
    ("override", "detail"),
    [
        ({"nonce": "other"}, "nonce"),
        ({"aud": "someone-else"}, "aud"),
        ({"aud": ["someone-else", "another"]}, "aud"),
        ({"iss": "https://evil.test"}, "iss"),
        ({"exp": 1}, "expired"),
        ({"nonce": None}, "nonce"),
        ({"sub": ...}, "sub"),
    ],
)
async def test_invalid_id_token_is_rejected(idp: FakeIdp, override: dict[str, object], detail: str) -> None:
    with pytest.raises(OidcLoginError) as caught:
        await _login(_client(idp), idp, **override)

    assert caught.value.code is OidcErrorCode.token_invalid, detail


async def test_unsigned_and_hmac_tokens_are_rejected(idp: FakeIdp) -> None:
    client = _client(idp)
    request = OidcAuthorizeRequest(_provider(), REDIRECT, "s", "nonce-1", CHALLENGE)
    await client.authorize_url(request)
    discovery = client._discovery[ISSUER]  # noqa: SLF001
    for alg in ("none", "HS256"):
        header = base64.urlsafe_b64encode(f'{{"alg":"{alg}","kid":"k1"}}'.encode()).rstrip(b"=").decode()
        with pytest.raises(OidcLoginError) as caught:
            await client._validate(_provider(), discovery, f"{header}.e30.", "nonce-1")  # noqa: SLF001
        assert caught.value.code is OidcErrorCode.token_invalid


async def test_token_signed_by_foreign_key_is_rejected(idp: FakeIdp) -> None:
    foreign = FakeIdp()
    token = foreign.id_token(nonce="nonce-1")
    idp.codes["c"] = IssuedCode("nonce-1", CHALLENGE, REDIRECT)
    idp.id_token = lambda **_: token  # type: ignore[method-assign]

    with pytest.raises(OidcLoginError) as caught:
        await _client(idp).exchange(
            _provider(), code="c", code_verifier=VERIFIER, redirect_uri=REDIRECT, nonce="nonce-1"
        )

    assert caught.value.code is OidcErrorCode.token_invalid


async def test_key_rotation_refetches_jwks(idp: FakeIdp) -> None:
    client = _client(idp, jwks_refetch_s=0)
    await _login(client, idp)

    idp.rotate("k2")
    claims = await _login(client, idp)

    assert claims.subject == "idp-user-1"
    assert idp.count("/certs") == 2


async def test_unknown_kid_does_not_hammer_the_provider(idp: FakeIdp) -> None:
    client = _client(idp, jwks_refetch_s=3600)
    await _login(client, idp)
    idp.rotate("k2")

    with pytest.raises(OidcLoginError) as caught:
        await _login(client, idp)

    assert caught.value.code is OidcErrorCode.token_invalid
    assert idp.count("/certs") == 1


async def test_retired_key_stops_working_after_rotation(idp: FakeIdp) -> None:
    client = _client(idp, jwks_refetch_s=0, jwks_ttl_s=0)
    old = idp.keys[0]
    await _login(client, idp)
    idp.rotate("k2")

    with pytest.raises(OidcLoginError):
        await _login(client, idp, key=old)


async def test_discovery_with_other_issuer_is_rejected(idp: FakeIdp) -> None:
    idp.discovery_issuer = "https://evil.test"

    with pytest.raises(OidcLoginError) as caught:
        await _client(idp).authorize_url(OidcAuthorizeRequest(_provider(), REDIRECT, "s", "n", CHALLENGE))

    assert caught.value.code is OidcErrorCode.discovery_failed


async def test_discovery_error_status_fails(idp: FakeIdp) -> None:
    idp.discovery_status = 500

    with pytest.raises(OidcLoginError) as caught:
        await _client(idp).authorize_url(OidcAuthorizeRequest(_provider(), REDIRECT, "s", "n", CHALLENGE))

    assert caught.value.code is OidcErrorCode.discovery_failed


async def test_token_endpoint_error_fails_exchange(idp: FakeIdp) -> None:
    client = _client(idp)
    code, _ = idp.authorize(
        await client.authorize_url(OidcAuthorizeRequest(_provider(), REDIRECT, "s", "nonce-1", CHALLENGE))
    )
    idp.token_status = 400

    with pytest.raises(OidcLoginError) as caught:
        await client.exchange(_provider(), code=code, code_verifier=VERIFIER, redirect_uri=REDIRECT, nonce="nonce-1")

    assert caught.value.code is OidcErrorCode.token_exchange_failed


async def test_wrong_pkce_verifier_fails_exchange(idp: FakeIdp) -> None:
    client = _client(idp)
    code, _ = idp.authorize(
        await client.authorize_url(OidcAuthorizeRequest(_provider(), REDIRECT, "s", "nonce-1", CHALLENGE))
    )

    with pytest.raises(OidcLoginError) as caught:
        await client.exchange(_provider(), code=code, code_verifier="x" * 64, redirect_uri=REDIRECT, nonce="nonce-1")

    assert caught.value.code is OidcErrorCode.token_exchange_failed


async def test_email_verified_string_and_missing_email(idp: FakeIdp) -> None:
    claims = await _login(_client(idp), idp, email_verified="true", email=...)

    assert claims.email is None
    assert claims.email_verified is True
