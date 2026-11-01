"""Выбор ключа бэкапа: из ключей установки или из парольной фразы. Чистые функции."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from hse_doc_studio.core.backup.crypto import key_check, key_from_installation, key_from_passphrase, key_matches
from hse_doc_studio.core.backup.entities import EncryptionMode, Manifest
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode


@dataclass(frozen=True)
class BackupKey:
    key: bytes
    salt: bytes
    mode: EncryptionMode
    check: str
    fingerprint: str | None


def fingerprint_of(raw_key: bytes) -> str:
    return hashlib.sha256(raw_key).hexdigest()[:12]


def make_key(mode: EncryptionMode, salt: bytes, *, installation_key: bytes | None, passphrase: str | None) -> BackupKey:
    """Ключ для нового бэкапа."""
    if mode is EncryptionMode.installation:
        if installation_key is None:
            raise BackupError(BackupErrorCode.secrets_unavailable, "installation key is not available")
        key = key_from_installation(installation_key, salt)
        return BackupKey(key, salt, mode, key_check(key), fingerprint_of(installation_key))
    if not passphrase:
        raise BackupError(BackupErrorCode.secrets_unavailable, "passphrase is not set", field="passphrase")
    key = key_from_passphrase(passphrase, salt)
    return BackupKey(key, salt, mode, key_check(key), None)


def open_key(manifest: Manifest, *, installation_keys: list[bytes], passphrase: str | None) -> bytes:
    """Ключ для чтения бэкапа: подходящий по проверочному значению манифеста, иначе отказ с понятной причиной."""
    salt = bytes.fromhex(manifest.salt_hex)
    if manifest.encryption_mode is EncryptionMode.passphrase:
        if not passphrase:
            raise BackupError(
                BackupErrorCode.secrets_unavailable,
                "the backup is encrypted with a passphrase: pass it",
                field="passphrase",
            )
        key = key_from_passphrase(passphrase, salt)
        if not key_matches(key, manifest.key_check):
            raise BackupError(BackupErrorCode.secrets_unavailable, "wrong passphrase", field="passphrase")
        return key
    for raw in installation_keys:
        key = key_from_installation(raw, salt)
        if key_matches(key, manifest.key_check):
            return key
    raise BackupError(
        BackupErrorCode.secrets_unavailable,
        "none of the installation keys (SECRETS_KEY, RETIRED_KEYS) opens this backup",
    )
