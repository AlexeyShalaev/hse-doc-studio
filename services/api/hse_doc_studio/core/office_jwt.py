"""Minimal HS256 JWT for the ONLYOFFICE Document Server integration.

DS «security tokens» — это обычные JWT (HS256) от общего секрета: бэкенд
подписывает конфиг редактора, DS подписывает колбэки. Тянуть pyjwt ради двух
функций не хочется — рукописная реализация на stdlib (hmac + base64url без
паддинга) полностью покрывает наш случай: alg зафиксирован, claims не
используются (без exp/aud), полезная нагрузка — произвольный dict.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

_HEADER = {"alg": "HS256", "typ": "JWT"}


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padded = segment + "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _signature(signing_input: bytes, secret: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()


def sign(payload: dict[str, Any], secret: str) -> str:
    """Sign a payload dict into a compact `header.payload.signature` JWT."""
    header_seg = _b64url_encode(json.dumps(_HEADER, separators=(",", ":")).encode("utf-8"))
    payload_seg = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    return f"{header_seg}.{payload_seg}.{_b64url_encode(_signature(signing_input, secret))}"


def verify(token: str, secret: str) -> dict[str, Any]:
    """Verify an HS256 JWT and return its payload; raise ValueError on any defect."""
    parts = token.split(".")
    if len(parts) != 3:  # header.payload.signature
        raise ValueError("malformed JWT: expected 3 segments")
    header_seg, payload_seg, signature_seg = parts
    try:
        header = json.loads(_b64url_decode(header_seg))
        provided = _b64url_decode(signature_seg)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed JWT: {exc}") from exc
    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise ValueError("unsupported JWT algorithm")
    signing_input = f"{header_seg}.{payload_seg}".encode("ascii")
    if not hmac.compare_digest(provided, _signature(signing_input, secret)):
        raise ValueError("JWT signature mismatch")
    try:
        payload = json.loads(_b64url_decode(payload_seg))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"malformed JWT payload: {exc}") from exc
    if not isinstance(payload, dict):
        # Осознанно ValueError, не TypeError: это дефект ТОКЕНА, а не типов в
        # коде — вызывающие ловят единый ValueError на любую проблему верификации.
        raise ValueError("JWT payload must be an object")  # noqa: TRY004
    return payload
