"""Подписанные токены редактора ONLYOFFICE: документ (скачать файл) и колбэк (сохранить правку).

Токен несёт проект, документ, путь файла, актора и его роль на момент выдачи, одноразовое число сессии
и срок. Роль в токене подсказка для журнала: при использовании права проверяются заново по `decide`.
Ключи производные от связки секретов, первичный первым: подписывает он, проверка перебирает все.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

OFFICE_TOKEN_KEY_PURPOSE = "office-token"  # noqa: S105 — назначение ключа, не секрет
_VERSION = "o1"
_PARTS = 3


class OfficeTokenPurpose(StrEnum):
    document = "document"
    callback = "callback"


class OfficeTokenError(Exception):
    """Токен не подходит: подпись, срок, назначение или адресат. Причину наружу не раскрываем."""


@dataclass(frozen=True)
class OfficeTokenClaims:
    purpose: OfficeTokenPurpose
    project_id: str
    doc_id: str
    path: str
    actor_id: str
    role: str
    nonce: str
    expires_at: datetime


def new_nonce() -> str:
    return secrets.token_urlsafe(12)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(key: bytes, signed: str) -> bytes:
    return hmac.new(key, signed.encode("ascii"), hashlib.sha256).digest()


class OfficeTokenSigner:
    def __init__(self, keys: Sequence[bytes]) -> None:
        if not keys:
            raise ValueError("нужен хотя бы один ключ")
        self._keys = tuple(keys)

    def sign(self, claims: OfficeTokenClaims) -> str:
        payload = json.dumps(
            {
                "u": claims.purpose.value,
                "p": claims.project_id,
                "d": claims.doc_id,
                "f": claims.path,
                "a": claims.actor_id,
                "r": claims.role,
                "n": claims.nonce,
                "e": int(claims.expires_at.timestamp()),
            },
            separators=(",", ":"),
            sort_keys=True,
            ensure_ascii=False,
        )
        signed = f"{_VERSION}.{_b64(payload.encode('utf-8'))}"
        return f"{signed}.{_b64(_mac(self._keys[0], signed))}"

    def verify(
        self,
        token: str,
        now: datetime,
        *,
        purpose: OfficeTokenPurpose,
        project_id: str | None = None,
        doc_id: str | None = None,
    ) -> OfficeTokenClaims:
        invalid = OfficeTokenError("office token invalid")
        parts = token.split(".")
        if len(parts) != _PARTS or parts[0] != _VERSION:
            raise invalid
        signed = f"{parts[0]}.{parts[1]}"
        try:
            given = _unb64(parts[2])
            raw = json.loads(_unb64(parts[1]))
            claims = OfficeTokenClaims(
                purpose=OfficeTokenPurpose(raw["u"]),
                project_id=str(raw["p"]),
                doc_id=str(raw["d"]),
                path=str(raw["f"]),
                actor_id=str(raw["a"]),
                role=str(raw["r"]),
                nonce=str(raw["n"]),
                expires_at=datetime.fromtimestamp(int(raw["e"]), tz=now.tzinfo),
            )
        except (ValueError, KeyError, TypeError, UnicodeError, OverflowError, OSError):
            raise invalid from None
        matched = False
        for key in self._keys:
            matched |= hmac.compare_digest(_mac(key, signed), given)
        if (
            not matched
            or claims.expires_at <= now
            or claims.purpose is not purpose
            or (project_id is not None and claims.project_id != project_id)
            or (doc_id is not None and claims.doc_id != doc_id)
        ):
            raise invalid
        return claims
