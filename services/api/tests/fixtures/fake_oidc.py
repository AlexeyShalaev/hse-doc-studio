"""Фейковый провайдер OIDC: discovery, JWKS, обмен кода и ID-токены с настоящими RSA-ключами.

Работает поверх httpx.MockTransport, сеть не нужна. Провайдер проверяет то, что проверил бы настоящий:
PKCE (S256), совпадение redirect_uri и учётные данные клиента.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
from joserfc import jwt
from joserfc.jwk import RSAKey

ISSUER = "https://idp.test/realms/hse"
CLIENT_ID = "studio"
CLIENT_SECRET = "s3cr3t-client"  # noqa: S105 — значение для теста


@dataclass
class IssuedCode:
    nonce: str
    challenge: str
    redirect_uri: str
    overrides: dict[str, Any] = field(default_factory=dict)


class FakeIdp:
    def __init__(self, *, issuer: str = ISSUER, client_id: str = CLIENT_ID, client_secret: str = CLIENT_SECRET) -> None:
        self.issuer = issuer
        self.client_id = client_id
        self.client_secret = client_secret
        self.keys: list[Any] = [self._new_key("k1")]
        self.codes: dict[str, IssuedCode] = {}
        self.requests: list[httpx.Request] = []
        self.discovery_status = 200
        self.token_status = 200
        self.auth_methods: list[str] | None = None
        self.discovery_issuer: str | None = None

    @staticmethod
    def _new_key(kid: str) -> Any:
        return RSAKey.generate_key(2048, parameters={"kid": kid, "use": "sig"})

    def rotate(self, kid: str = "k2", *, keep_old: bool = False) -> Any:
        """Провайдер выпускает новый ключ; старый по умолчанию пропадает из набора."""
        new = self._new_key(kid)
        self.keys = [*self.keys, new] if keep_old else [new]
        return new

    def count(self, suffix: str) -> int:
        return sum(1 for request in self.requests if request.url.path.endswith(suffix))

    # Протокол

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))

    def authorize(self, url: str, **overrides: Any) -> tuple[str, str]:
        """Человек вошёл у провайдера: по адресу авторизации выдаём код и возвращаем (код, state)."""
        parts = urlsplit(url)
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        assert parts.geturl().startswith(f"{self.issuer}/protocol/openid-connect/auth")
        assert query["response_type"] == "code"
        assert query["client_id"] == self.client_id
        assert query["code_challenge_method"] == "S256"
        code = secrets.token_urlsafe(12)
        self.codes[code] = IssuedCode(query["nonce"], query["code_challenge"], query["redirect_uri"], overrides)
        return code, query["state"]

    def id_token(
        self,
        *,
        nonce: str | None,
        sub: str = "idp-user-1",
        key: Any = None,
        alg: str = "RS256",
        **claims: Any,
    ) -> str:
        now = int(time.time())
        payload: dict[str, Any] = {
            "iss": self.issuer,
            "aud": self.client_id,
            "sub": sub,
            "iat": now,
            "exp": now + 3600,
            "email": "ann@example.org",
            "email_verified": True,
            "name": "Ann",
        }
        if nonce is not None:
            payload["nonce"] = nonce
        payload |= claims
        payload = {k: v for k, v in payload.items() if v is not ...}
        signing = key or self.keys[-1]
        header = {"alg": alg, "kid": signing.kid}
        return jwt.encode(header, payload, signing, algorithms=[alg])

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.endswith("/.well-known/openid-configuration"):
            if self.discovery_status != 200:
                return httpx.Response(self.discovery_status)
            doc: dict[str, Any] = {
                "issuer": self.discovery_issuer or self.issuer,
                "authorization_endpoint": f"{self.issuer}/protocol/openid-connect/auth",
                "token_endpoint": f"{self.issuer}/protocol/openid-connect/token",
                "jwks_uri": f"{self.issuer}/protocol/openid-connect/certs",
            }
            if self.auth_methods is not None:
                doc["token_endpoint_auth_methods_supported"] = self.auth_methods
            return httpx.Response(200, json=doc)
        if path.endswith("/certs"):
            return httpx.Response(200, json={"keys": [key.as_dict(private=False) for key in self.keys]})
        if path.endswith("/token"):
            return self._token(request)
        return httpx.Response(404)

    def _token(self, request: httpx.Request) -> httpx.Response:
        if self.token_status != 200:
            return httpx.Response(self.token_status, json={"error": "invalid_grant"})
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if not self._client_ok(request, form):
            return httpx.Response(401, json={"error": "invalid_client"})
        issued = self.codes.pop(form.get("code", ""), None)
        if issued is None or form.get("redirect_uri") != issued.redirect_uri:
            return httpx.Response(400, json={"error": "invalid_grant"})
        digest = hashlib.sha256(form.get("code_verifier", "").encode()).digest()
        if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != issued.challenge:
            return httpx.Response(400, json={"error": "invalid_grant", "error_description": "PKCE"})
        overrides = dict(issued.overrides)
        nonce = overrides.pop("nonce", issued.nonce)
        token = self.id_token(nonce=nonce, **overrides)
        return httpx.Response(200, json={"access_token": "at", "token_type": "Bearer", "id_token": token})

    def _client_ok(self, request: httpx.Request, form: dict[str, str]) -> bool:
        header = request.headers.get("authorization", "")
        if header.startswith("Basic "):
            raw = base64.b64decode(header[6:]).decode()
            return raw == f"{self.client_id}:{self.client_secret}"
        return form.get("client_id") == self.client_id and form.get("client_secret") == self.client_secret
