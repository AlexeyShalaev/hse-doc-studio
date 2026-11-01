"""Шифр секретов на Fernet с конвертом `hs1:<идентификатор ключа>:<токен Fernet>`.

Идентификатор ключа в конверте позволяет точно отличить «ключа нет» от «шифртекст повреждён» и
готов к смене ключа: расшифровать можно любым ключом связки (файл или RETIRED_KEYS), писать будет первичный.
У Fernet нет AAD, поэтому привязка к записи сделана приставкой: перед секретом кладётся `aad`
и нулевой байт, после расшифровки приставка сверяется, и шифртекст, перенесённый из одной записи
в другую, не откроется.
"""

from __future__ import annotations

import hmac

import structlog
from cryptography.fernet import Fernet, InvalidToken

from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.secret import CipherStatus, Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.infra.secrets.key_ring import ENV_KEY_ID, KeyRing
from hse_doc_studio.infra.secrets.key_store import KeyFileStore

logger = structlog.get_logger()

_ENVELOPE_PREFIX = "hs1"
_SEPARATOR = b"\x00"


def _unreadable() -> GitSyncError:
    return GitSyncError(
        GitErrorCode.secrets_unavailable,
        localized_error(
            "Не удалось расшифровать сохранённый секрет: ключа нет или он не подходит. Введите токен заново.",
            "The saved secret cannot be decrypted: the key is missing or does not match. Enter the token again.",
        ),
    )


def _split(token: str) -> tuple[str, str] | None:
    parts = token.split(":", 2)
    if len(parts) != 3 or parts[0] != _ENVELOPE_PREFIX or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def _may_be_retired(key_id: str, ring: KeyRing) -> bool:
    # Конверт прежнего первичного ключа несёт его старый идентификатор: найти ключ можно только перебором.
    return key_id == ENV_KEY_ID and len(ring.keys) > 1


def _open(ring: KeyRing, key_id: str, sealed: str) -> bytes | None:
    for key in ring.candidates(key_id):
        try:
            return Fernet(key).decrypt(sealed.encode())
        except InvalidToken:
            continue
    return None


class FernetSecretCipher:
    def __init__(self, key_store: KeyFileStore) -> None:
        self._keys = key_store

    def encrypt(self, plaintext: Secret, *, aad: str) -> str:
        ring = self._keys.ensure_primary()
        payload = aad.encode() + _SEPARATOR + plaintext.reveal().encode()
        sealed = Fernet(ring.keys[ring.primary_id]).encrypt(payload).decode()
        return f"{_ENVELOPE_PREFIX}:{ring.primary_id}:{sealed}"

    def decrypt(self, token: str, *, aad: str, legacy_aad: str | None = None) -> Secret:
        """`legacy_aad` читает записи, сделанные до перехода на привязку таблица/колонка/id; пишется всегда новая."""
        parsed = _split(token)
        ring = self._keys.load()
        if parsed is None or ring is None or not (parsed[0] in ring.keys or _may_be_retired(parsed[0], ring)):
            logger.warning("secret cannot be decrypted", reason="no_key_or_bad_envelope")
            raise _unreadable()
        key_id, sealed = parsed
        payload = _open(ring, key_id, sealed)
        if payload is None:
            logger.warning("secret cannot be decrypted", reason="tampered_or_wrong_key", key_id=key_id)
            raise _unreadable()
        for expected in (aad, legacy_aad):
            prefix = (expected or "").encode() + _SEPARATOR
            if expected is not None and hmac.compare_digest(payload[: len(prefix)], prefix):
                return Secret(payload[len(prefix) :].decode())
        logger.warning("secret cannot be decrypted", reason="bound_to_another_record", key_id=key_id)
        raise _unreadable()

    def is_current(self, token: str) -> bool:
        """Записан ли шифртекст первичным ключом: иначе его пора перешифровать (`secrets reencrypt`)."""
        parsed = _split(token)
        ring = self._keys.load()
        if parsed is None or ring is None:
            return False
        try:
            Fernet(ring.primary).decrypt(parsed[1].encode())
        except InvalidToken:
            return False
        return True

    def can_read(self, token: str) -> bool:
        parsed = _split(token)
        ring = self._keys.load()
        return parsed is not None and ring is not None and parsed[0] in ring.keys

    def status(self) -> CipherStatus:
        return self._keys.status()
