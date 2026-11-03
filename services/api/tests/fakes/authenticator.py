"""Программный аутентификатор WebAuthn для тестов: настоящие ответы регистрации и входа (attestation none, ES256).

Ответы подписаны настоящим ключом P-256, поэтому их проверяет та же библиотека, что и в работе. Флаги, счётчик,
origin и RP ID задаются явно: так тесты получают и годные ответы, и каждую порчу по отдельности.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass, field

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

FLAG_UP = 0x01
FLAG_UV = 0x04
FLAG_BE = 0x08
FLAG_BS = 0x10
FLAG_AT = 0x40

type Json = dict[str, object]


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _cbor_head(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([major << 5 | value])
    for extra, size in ((24, 1), (25, 2), (26, 4), (27, 8)):
        if value < 1 << (8 * size):
            return bytes([major << 5 | extra]) + value.to_bytes(size, "big")
    raise ValueError(value)


def cbor(value: object) -> bytes:
    """Минимальный CBOR (RFC 8949) для структур WebAuthn: целые, байты, строки, словари."""
    if isinstance(value, bool):
        raise TypeError("bool")
    if isinstance(value, int):
        return _cbor_head(0, value) if value >= 0 else _cbor_head(1, -1 - value)
    if isinstance(value, bytes):
        return _cbor_head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return _cbor_head(3, len(raw)) + raw
    if isinstance(value, dict):
        return _cbor_head(5, len(value)) + b"".join(cbor(k) + cbor(v) for k, v in value.items())
    raise TypeError(type(value))


@dataclass
class SoftCredential:
    credential_id: bytes
    key: ec.EllipticCurvePrivateKey
    rp_id: str
    user_handle: bytes
    sign_count: int = 0

    @property
    def id(self) -> str:
        return b64url(self.credential_id)


@dataclass
class SoftAuthenticator:
    """Один «телефон»: держит ключи, считает подписи (или держит счётчик нулём, как синхронизируемые passkey)."""

    origin: str = "https://studio.test"
    counter: bool = True
    synced: bool = False
    credentials: list[SoftCredential] = field(default_factory=list)

    def _flags(self, *, uv: bool, attested: bool = False) -> int:
        flags = FLAG_UP | (FLAG_UV if uv else 0) | (FLAG_AT if attested else 0)
        return flags | (FLAG_BE | FLAG_BS if self.synced else 0)

    def _client_data(self, kind: str, challenge: str, origin: str | None) -> bytes:
        body = {"type": kind, "challenge": challenge, "origin": origin or self.origin, "crossOrigin": False}
        return json.dumps(body, separators=(",", ":")).encode()

    def create(
        self,
        options: Json,
        *,
        uv: bool = True,
        origin: str | None = None,
        rp_id: str | None = None,
    ) -> Json:
        """Ответ `navigator.credentials.create()` на параметры сервера."""
        rp = options["rp"]
        user = options["user"]
        assert isinstance(rp, dict)  # noqa: S101
        assert isinstance(user, dict)  # noqa: S101
        target_rp = rp_id or str(rp["id"])
        key = ec.generate_private_key(ec.SECP256R1())
        numbers = key.public_key().public_numbers()
        cose = cbor({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"), -3: numbers.y.to_bytes(32, "big")})
        credential_id = secrets.token_bytes(16)
        attested = bytes(16) + len(credential_id).to_bytes(2, "big") + credential_id + cose
        auth_data = (
            hashlib.sha256(target_rp.encode()).digest()
            + bytes([self._flags(uv=uv, attested=True)])
            + (0).to_bytes(4, "big")
            + attested
        )
        attestation = cbor({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = self._client_data("webauthn.create", str(options["challenge"]), origin)
        self.credentials.append(SoftCredential(credential_id, key, target_rp, b64url_decode(str(user["id"]))))
        return {
            "id": b64url(credential_id),
            "rawId": b64url(credential_id),
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": b64url(client_data),
                "attestationObject": b64url(attestation),
                "transports": ["internal", "hybrid"],
            },
        }

    def get(
        self,
        options: Json,
        *,
        credential: SoftCredential | None = None,
        uv: bool = True,
        origin: str | None = None,
        sign_count: int | None = None,
        user_handle: bytes | None = None,
    ) -> Json:
        """Ответ `navigator.credentials.get()`: по умолчанию последним созданным ключом."""
        cred = credential or self.credentials[-1]
        if sign_count is None:
            if self.counter:
                cred.sign_count += 1
            sign_count = cred.sign_count if self.counter else 0
        auth_data = (
            hashlib.sha256(cred.rp_id.encode()).digest() + bytes([self._flags(uv=uv)]) + sign_count.to_bytes(4, "big")
        )
        client_data = self._client_data("webauthn.get", str(options["challenge"]), origin)
        signature = cred.key.sign(auth_data + hashlib.sha256(client_data).digest(), ec.ECDSA(hashes.SHA256()))
        return {
            "id": cred.id,
            "rawId": cred.id,
            "type": "public-key",
            "authenticatorAttachment": "platform",
            "clientExtensionResults": {},
            "response": {
                "clientDataJSON": b64url(client_data),
                "authenticatorData": b64url(auth_data),
                "signature": b64url(signature),
                "userHandle": b64url(user_handle if user_handle is not None else cred.user_handle),
            },
        }
