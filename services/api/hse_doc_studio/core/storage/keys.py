"""Ключи объектов: общий словарь для диска и S3."""

from __future__ import annotations

import re

from hse_doc_studio.core.storage.errors import InvalidObjectKeyError

MAX_KEY_LENGTH = 1024
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def is_sha256(value: str) -> bool:
    return _SHA256_RE.fullmatch(value) is not None


def blob_key(sha256: str) -> str:
    """Ключ блоба: `blobs/<первые два символа>/<sha256>`; нечестный хеш не даёт ключа."""
    if not is_sha256(sha256):
        msg = "sha256 должен быть 64 строчными шестнадцатеричными цифрами"
        raise InvalidObjectKeyError(msg)
    return f"blobs/{sha256[:2]}/{sha256}"


def validate_key(key: str) -> str:
    """Возвращает ключ, если он безопасен как путь на диске и как ключ S3.

    Сегменты разделяет `/`; пустой сегмент, сегмент с точки, обратная косая и управляющие символы отвергаются:
    скрытые имена нужны реализации на диске для временных файлов.
    """
    if not key or len(key.encode("utf-8")) > MAX_KEY_LENGTH:
        msg = "ключ пустой или длиннее 1024 байт"
        raise InvalidObjectKeyError(msg)
    if "\\" in key or any(ord(ch) < 32 or ord(ch) == 127 for ch in key):
        msg = "ключ содержит обратную косую или управляющий символ"
        raise InvalidObjectKeyError(msg)
    for segment in key.split("/"):
        if not segment or segment.startswith("."):
            msg = "ключ содержит пустой сегмент или сегмент с точки"
            raise InvalidObjectKeyError(msg)
    return key
