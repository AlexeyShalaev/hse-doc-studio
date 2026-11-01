"""Клиент OIDC: описание провайдера (discovery) с кэшем, обмен кода и проверка ID-токена.

Подпись проверяется по ключам провайдера (JWKS). Незнакомый `kid` означает возможную ротацию ключей:
набор перечитывается, но не чаще раза в `jwks_refetch_s`, чтобы чужой токен не превращался в поток запросов.
Алгоритмы только асимметричные: `none` и HMAC (где ключом стал бы секрет клиента) не принимаются.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx
from joserfc import jwk, jwt
from joserfc.errors import JoseError

from hse_doc_studio.core.egress import EgressPurpose, IEgressPolicy
from hse_doc_studio.core.identity.oidc import (
    OidcAuthorizeRequest,
    OidcClaims,
    OidcErrorCode,
    OidcLoginError,
    OidcProviderConfig,
)
from hse_doc_studio.infra.egress.http import egress_client

logger = logging.getLogger(__name__)

ALLOWED_ALGORITHMS = ("RS256", "RS384", "RS512", "PS256", "PS384", "PS512", "ES256", "ES384", "ES512", "EdDSA")
_MAX_BODY = 1_000_000
_LEEWAY_S = 60
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
Clock = Callable[[], float]


@dataclass(frozen=True)
class _Discovery:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    token_auth_methods: tuple[str, ...]
    fetched_at: float


@dataclass
class _Jwks:
    keys: list[dict[str, Any]]
    fetched_at: float


def _secure_url(url: str) -> bool:
    parts = urlsplit(url)
    return bool(parts.hostname) and (
        parts.scheme == "https" or (parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS)
    )


def _same_issuer(left: str, right: str) -> bool:
    return left.rstrip("/") == right.rstrip("/")


def _truthy(value: object) -> bool:
    # Часть провайдеров (старые Cognito, Azure B2C) присылает "true" строкой.
    return value is True or (isinstance(value, str) and value.lower() == "true")


class OidcClient:
    def __init__(
        self,
        egress: IEgressPolicy | None = None,
        *,
        http: httpx.AsyncClient | None = None,
        discovery_ttl_s: float = 3600,
        jwks_ttl_s: float = 3600,
        jwks_refetch_s: float = 30,
        timeout_s: float = 10,
        clock: Clock = time.time,
    ) -> None:
        self._egress = egress
        self._http = http
        self._discovery_ttl = discovery_ttl_s
        self._jwks_ttl = jwks_ttl_s
        self._jwks_refetch = jwks_refetch_s
        self._timeout = timeout_s
        self._clock = clock
        self._discovery: dict[str, _Discovery] = {}
        self._jwks: dict[str, _Jwks] = {}

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    # Порт IOidcClient

    async def authorize_url(self, request: OidcAuthorizeRequest) -> str:
        discovery = await self._discover(request.provider)
        query = urlencode(
            {
                "response_type": "code",
                "client_id": request.provider.client_id,
                "redirect_uri": request.redirect_uri,
                "scope": request.provider.scopes,
                "state": request.state,
                "nonce": request.nonce,
                "code_challenge": request.code_challenge,
                "code_challenge_method": "S256",
            }
        )
        separator = "&" if "?" in discovery.authorization_endpoint else "?"
        return f"{discovery.authorization_endpoint}{separator}{query}"

    async def exchange(
        self, provider: OidcProviderConfig, *, code: str, code_verifier: str, redirect_uri: str, nonce: str
    ) -> OidcClaims:
        discovery = await self._discover(provider)
        tokens = await self._token_request(provider, discovery, code, code_verifier, redirect_uri)
        id_token = tokens.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OidcLoginError(OidcErrorCode.token_invalid, "no id_token")
        claims = await self._validate(provider, discovery, id_token, nonce)
        email = claims.get("email")
        name = claims.get("name") or claims.get("preferred_username")
        return OidcClaims(
            provider_id=provider.id,
            subject=str(claims["sub"]),
            email=email if isinstance(email, str) and email else None,
            email_verified=_truthy(claims.get("email_verified")),
            name=name if isinstance(name, str) and name else None,
        )

    # Провайдер

    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            if self._egress is not None:
                # Адрес провайдера задал администратор установки: допустим и внутренний (Keycloak в локальной сети).
                self._http = egress_client(
                    self._egress, EgressPurpose.admin, timeout=self._timeout, follow_redirects=False
                )
            else:
                self._http = httpx.AsyncClient(timeout=self._timeout, follow_redirects=False, trust_env=False)
        return self._http

    async def _get_json(self, url: str, failure: OidcErrorCode) -> Any:
        try:
            async with self._client().stream("GET", url, headers={"Accept": "application/json"}) as response:
                body = await _read_limited(response)
                if response.status_code != 200:
                    raise OidcLoginError(failure, f"{url} answered {response.status_code}")
            return json.loads(body)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise OidcLoginError(failure, f"{url}: {type(exc).__name__}") from exc

    async def _discover(self, provider: OidcProviderConfig) -> _Discovery:
        cached = self._discovery.get(provider.issuer)
        now = self._clock()
        if cached is not None and now - cached.fetched_at < self._discovery_ttl:
            return cached
        url = provider.issuer.rstrip("/") + "/.well-known/openid-configuration"
        data = await self._get_json(url, OidcErrorCode.discovery_failed)
        if not isinstance(data, dict) or not _same_issuer(str(data.get("issuer", "")), provider.issuer):
            raise OidcLoginError(OidcErrorCode.discovery_failed, "issuer mismatch")
        endpoints = {key: data.get(key) for key in ("authorization_endpoint", "token_endpoint", "jwks_uri")}
        if not all(isinstance(value, str) and _secure_url(value) for value in endpoints.values()):
            raise OidcLoginError(OidcErrorCode.discovery_failed, "bad endpoints")
        methods = data.get("token_endpoint_auth_methods_supported")
        discovery = _Discovery(
            issuer=str(data["issuer"]),
            authorization_endpoint=str(endpoints["authorization_endpoint"]),
            token_endpoint=str(endpoints["token_endpoint"]),
            jwks_uri=str(endpoints["jwks_uri"]),
            token_auth_methods=tuple(str(m) for m in methods) if isinstance(methods, list) else (),
            fetched_at=now,
        )
        self._discovery[provider.issuer] = discovery
        return discovery

    # Обмен кода

    async def _token_request(
        self, provider: OidcProviderConfig, discovery: _Discovery, code: str, verifier: str, redirect_uri: str
    ) -> dict[str, Any]:
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
        headers = {"Accept": "application/json"}
        methods = discovery.token_auth_methods
        if methods and "client_secret_basic" not in methods and "client_secret_post" in methods:
            form |= {"client_id": provider.client_id, "client_secret": provider.client_secret}
        else:
            # По RFC 6749 логин и секрет в Basic сначала кодируются как form-urlencoded.
            pair = f"{urlencode({'': provider.client_id})[1:]}:{urlencode({'': provider.client_secret})[1:]}"
            headers["Authorization"] = "Basic " + base64.b64encode(pair.encode()).decode("ascii")
        try:
            async with self._client().stream("POST", discovery.token_endpoint, data=form, headers=headers) as response:
                body = await _read_limited(response)
                status = response.status_code
            data = json.loads(body)
        except (httpx.HTTPError, OSError, ValueError) as exc:
            raise OidcLoginError(OidcErrorCode.token_exchange_failed, type(exc).__name__) from exc
        if status != 200 or not isinstance(data, dict) or "error" in data:
            error = data.get("error") if isinstance(data, dict) else None
            raise OidcLoginError(OidcErrorCode.token_exchange_failed, f"status {status} {str(error)[:64]}".strip())
        return data

    # ID-токен

    async def _validate(
        self, provider: OidcProviderConfig, discovery: _Discovery, id_token: str, nonce: str
    ) -> dict[str, Any]:
        try:
            header = json.loads(_b64decode(id_token.split(".", 1)[0]))
        except (ValueError, IndexError) as exc:
            raise OidcLoginError(OidcErrorCode.token_invalid, "malformed") from exc
        if not isinstance(header, dict) or header.get("alg") not in ALLOWED_ALGORITHMS:
            raise OidcLoginError(OidcErrorCode.token_invalid, f"alg {str(header.get('alg'))[:16]!r}")
        jwk_data = await self._find_key(discovery, header.get("kid"))
        if jwk_data is None:
            raise OidcLoginError(OidcErrorCode.token_invalid, "unknown key")
        try:
            token = jwt.decode(id_token, jwk.import_key(jwk_data), algorithms=list(ALLOWED_ALGORITHMS))
            registry = jwt.JWTClaimsRegistry(
                now=int(self._clock()),
                leeway=_LEEWAY_S,
                iss={"essential": True, "value": discovery.issuer},
                sub={"essential": True},
                exp={"essential": True},
                nonce={"essential": True, "value": nonce},
            )
            registry.validate(token.claims)
            _check_audience(token.claims, provider.client_id)
        except (JoseError, ValueError, TypeError, KeyError) as exc:
            raise OidcLoginError(OidcErrorCode.token_invalid, f"{type(exc).__name__}: {exc}"[:200]) from exc
        claims = token.claims
        if not isinstance(claims.get("nonce"), str):
            raise OidcLoginError(OidcErrorCode.token_invalid, "no nonce")
        if not isinstance(claims.get("sub"), str) or not claims["sub"]:
            raise OidcLoginError(OidcErrorCode.token_invalid, "no sub")
        return dict(claims)

    async def _find_key(self, discovery: _Discovery, kid: object) -> dict[str, Any] | None:
        cached = self._jwks.get(discovery.jwks_uri)
        now = self._clock()
        if cached is None or now - cached.fetched_at >= self._jwks_ttl:
            cached = await self._load_jwks(discovery)
        found = _pick_key(cached.keys, kid)
        if found is None and now - cached.fetched_at >= self._jwks_refetch:
            cached = await self._load_jwks(discovery)
            found = _pick_key(cached.keys, kid)
        return found

    async def _load_jwks(self, discovery: _Discovery) -> _Jwks:
        data = await self._get_json(discovery.jwks_uri, OidcErrorCode.token_invalid)
        keys = data.get("keys") if isinstance(data, dict) else None
        if not isinstance(keys, list):
            raise OidcLoginError(OidcErrorCode.token_invalid, "bad jwks")
        loaded = _Jwks([key for key in keys if isinstance(key, dict)], self._clock())
        self._jwks[discovery.jwks_uri] = loaded
        return loaded


def _check_audience(claims: dict[str, Any], client_id: str) -> None:
    """aud содержит нашего клиента; если получателей несколько, выдача должна быть адресована нам (azp)."""
    aud = claims.get("aud")
    audiences = [aud] if isinstance(aud, str) else aud
    if not isinstance(audiences, list) or client_id not in audiences:
        msg = "audience mismatch"
        raise ValueError(msg)
    azp = claims.get("azp")
    if (len(audiences) > 1 and azp is None) or (azp is not None and azp != client_id):
        msg = "authorized party mismatch"
        raise ValueError(msg)


def _pick_key(keys: list[dict[str, Any]], kid: object) -> dict[str, Any] | None:
    signing = [key for key in keys if key.get("use", "sig") == "sig"]
    if isinstance(kid, str):
        return next((key for key in signing if key.get("kid") == kid), None)
    return signing[0] if len(signing) == 1 else None


def _b64decode(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


async def _read_limited(response: httpx.Response) -> bytes:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body += chunk
        if len(body) > _MAX_BODY:
            msg = "response too large"
            raise ValueError(msg)
    return bytes(body)
