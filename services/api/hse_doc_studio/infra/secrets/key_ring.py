"""Связка ключей шифрования секретов: первичный пишет, прежние только читают.

Прежние ключи получают идентификатор по отпечатку: так конверт, записанный ключом, который потом
вывели из обращения, всё равно находит свой ключ. Конверты старого первичного ключа (`env`) после смены
ключа открываются перебором прежних ключей: Fernet сам отличает свой ключ по подписи.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ENV_KEY_ID = "env"
_DERIVED_LENGTH = 32
_INFO_PREFIX = b"hse-doc-studio/"


@dataclass(frozen=True)
class KeyRing:
    """Ключи Fernet по идентификаторам и тот, которым шифруются новые секреты."""

    primary_id: str
    keys: dict[str, bytes]

    @property
    def primary(self) -> bytes:
        return self.keys[self.primary_id]

    def candidates(self, key_id: str) -> list[bytes]:
        """Ключи для расшифровки конверта: сначала названный в нём, затем остальные."""
        first = self.keys.get(key_id)
        rest = [key for kid, key in self.keys.items() if kid != key_id]
        return [first, *rest] if first is not None else rest

    def derive(self, purpose: str, *, key: bytes | None = None) -> bytes:
        """Производный ключ под назначение (HMAC job-token, setup-токен): сырой ключ наружу не уходит."""
        return derive_key(key or self.primary, purpose)

    def derive_all(self, purpose: str) -> list[bytes]:
        """Производные ключи всех ключей связки, первичный первым: проверка подписи переживает смену ключа."""
        ordered = [self.primary, *(key for kid, key in self.keys.items() if kid != self.primary_id)]
        return [derive_key(key, purpose) for key in ordered]


def derive_key(key: bytes, purpose: str) -> bytes:
    raw = base64.urlsafe_b64decode(key)
    return HKDF(
        algorithm=hashes.SHA256(), length=_DERIVED_LENGTH, salt=None, info=_INFO_PREFIX + purpose.encode()
    ).derive(raw)


def fernet_key(raw: str) -> bytes | None:
    key = raw.strip().encode()
    try:
        Fernet(key)
    except (ValueError, TypeError):
        return None
    return key


def key_fingerprint(key: bytes) -> str:
    return "r" + hashlib.sha256(key).hexdigest()[:8]


def parse_retired_keys(raw: str | None) -> dict[str, bytes] | None:
    """Прежние ключи из списка через запятую или перевод строки; None, если хоть один негоден."""
    keys: dict[str, bytes] = {}
    for part in (raw or "").replace("\n", ",").split(","):
        if not part.strip():
            continue
        key = fernet_key(part)
        if key is None:
            return None
        keys[key_fingerprint(key)] = key
    return keys
