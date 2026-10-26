"""Шифр секретов на Fernet с конвертом `hs1:<идентификатор ключа>:<токен Fernet>`.

Идентификатор ключа в конверте позволяет точно отличить «ключа нет» от «шифртекст повреждён» и
готов к смене ключа: расшифровать можно любым ключом из файла, писать будет первичный.
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
from hse_doc_studio.infra.git_sync.key_store import KeyFileStore

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


class FernetSecretCipher:
    def __init__(self, key_store: KeyFileStore) -> None:
        self._keys = key_store

    def encrypt(self, plaintext: Secret, *, aad: str) -> str:
        ring = self._keys.ensure_primary()
        payload = aad.encode() + _SEPARATOR + plaintext.reveal().encode()
        sealed = Fernet(ring.keys[ring.primary_id]).encrypt(payload).decode()
        return f"{_ENVELOPE_PREFIX}:{ring.primary_id}:{sealed}"

    def decrypt(self, token: str, *, aad: str) -> Secret:
        parsed = _split(token)
        ring = self._keys.load()
        if parsed is None or ring is None or parsed[0] not in ring.keys:
            logger.warning("secret cannot be decrypted", reason="no_key_or_bad_envelope")
            raise _unreadable()
        key_id, sealed = parsed
        try:
            payload = Fernet(ring.keys[key_id]).decrypt(sealed.encode())
        except InvalidToken:
            logger.warning("secret cannot be decrypted", reason="tampered_or_wrong_key", key_id=key_id)
            raise _unreadable() from None
        prefix = aad.encode() + _SEPARATOR
        if not hmac.compare_digest(payload[: len(prefix)], prefix):
            logger.warning("secret cannot be decrypted", reason="bound_to_another_record", key_id=key_id)
            raise _unreadable()
        return Secret(payload[len(prefix) :].decode())

    def can_read(self, token: str) -> bool:
        parsed = _split(token)
        ring = self._keys.load()
        return parsed is not None and ring is not None and parsed[0] in ring.keys

    def status(self) -> CipherStatus:
        return self._keys.status()
