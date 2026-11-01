"""Потоковое шифрование частей бэкапа: AES-256-GCM блоками по 1 МиБ.

Формат: заголовок (магия, размер блока, случайный префикс nonce), затем блоки `шифртекст + тег`. Nonce блока это
префикс и счётчик; AAD блока это заголовок, номер блока и признак последнего. Поэтому подмена заголовка,
перестановка и усечение блоков не проходят проверку тега. Ключ один на весь бэкап (соль в манифесте), префикс nonce
у каждой части свой.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import BinaryIO

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"HSEBK\x01"
CHUNK_SIZE = 1024 * 1024
KEY_LENGTH = 32
SALT_LENGTH = 16
_PREFIX_LENGTH = 8
_TAG_LENGTH = 16
_HEADER = struct.Struct(">6sI8s")
HEADER_LENGTH = _HEADER.size
_MAX_CHUNK = 64 * 1024 * 1024
_KEY_CHECK_LABEL = b"hse-doc-studio/backup/key-check"
_HKDF_INFO = b"hse-doc-studio/backup/v1"
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1


class BackupCryptoError(Exception):
    """Шифртекст повреждён, усечён или ключ не подходит."""


def new_salt() -> bytes:
    return os.urandom(SALT_LENGTH)


def key_from_installation(raw_key: bytes, salt: bytes) -> bytes:
    """Ключ из первичного ключа установки (сырые 32 байта Fernet-ключа)."""
    return HKDF(algorithm=hashes.SHA256(), length=KEY_LENGTH, salt=salt, info=_HKDF_INFO).derive(raw_key)


def key_from_passphrase(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=KEY_LENGTH, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P).derive(passphrase.encode())


def key_check(key: bytes) -> str:
    """Проверочное значение ключа для манифеста: не раскрывает ключ, но отличает неверный."""
    return hmac.new(key, _KEY_CHECK_LABEL, hashlib.sha256).hexdigest()[:32]


def key_matches(key: bytes, expected_check: str) -> bool:
    return hmac.compare_digest(key_check(key), expected_check)


def _nonce(prefix: bytes, index: int) -> bytes:
    return prefix + struct.pack(">I", index)


def _aad(header: bytes, index: int, last: bool) -> bytes:
    return header + struct.pack(">I?", index, last)


@dataclass(frozen=True)
class StreamStats:
    """Что прошло через поток: размер и sha256 открытого текста и шифртекста."""

    plain_size: int
    plain_sha256: str
    cipher_size: int
    cipher_sha256: str


class EncryptingWriter:
    """Приёмник открытого текста, пишущий шифртекст в `sink`. `close()` обязателен: пишет последний блок."""

    def __init__(self, sink: BinaryIO, key: bytes, *, chunk_size: int = CHUNK_SIZE) -> None:
        if len(key) != KEY_LENGTH:
            msg = "ключ должен быть 32 байта"
            raise BackupCryptoError(msg)
        self._sink = sink
        self._aead = AESGCM(key)
        self._chunk = chunk_size
        prefix = os.urandom(_PREFIX_LENGTH)
        self._header = _HEADER.pack(MAGIC, chunk_size, prefix)
        self._prefix = prefix
        self._buffer = bytearray()
        self._index = 0
        self._closed = False
        self._plain = hashlib.sha256()
        self._cipher = hashlib.sha256()
        self._plain_size = 0
        self._cipher_size = 0
        self._emit(self._header)

    def _emit(self, data: bytes) -> None:
        self._sink.write(data)
        self._cipher.update(data)
        self._cipher_size += len(data)

    def _seal(self, data: bytes, *, last: bool) -> None:
        sealed = self._aead.encrypt(_nonce(self._prefix, self._index), data, _aad(self._header, self._index, last))
        self._index += 1
        self._emit(sealed)

    def write(self, data: bytes | bytearray | memoryview) -> int:
        if self._closed:
            msg = "поток шифрования закрыт"
            raise ValueError(msg)
        view = bytes(data)
        self._plain.update(view)
        self._plain_size += len(view)
        self._buffer += view
        # Последний блок должен остаться в буфере до close(): только он несёт признак last.
        while len(self._buffer) > self._chunk:
            self._seal(bytes(self._buffer[: self._chunk]), last=False)
            del self._buffer[: self._chunk]
        return len(view)

    def flush(self) -> None:
        return None

    def close(self) -> StreamStats:
        if not self._closed:
            self._closed = True
            self._seal(bytes(self._buffer), last=True)
            self._buffer.clear()
        return self.stats

    @property
    def stats(self) -> StreamStats:
        return StreamStats(self._plain_size, self._plain.hexdigest(), self._cipher_size, self._cipher.hexdigest())


class DecryptingReader:
    """Читает шифртекст из `source` и отдаёт открытый текст; неверный тег или усечение это `BackupCryptoError`."""

    def __init__(self, source: BinaryIO, key: bytes) -> None:
        header = source.read(HEADER_LENGTH)
        if len(header) != HEADER_LENGTH:
            msg = "шифртекст короче заголовка"
            raise BackupCryptoError(msg)
        magic, chunk_size, prefix = _HEADER.unpack(header)
        if magic != MAGIC or not 0 < chunk_size <= _MAX_CHUNK:
            msg = "это не шифртекст бэкапа или формат неизвестен"
            raise BackupCryptoError(msg)
        self._source = source
        self._aead = AESGCM(key)
        self._header = header
        self._prefix = prefix
        self._chunk = chunk_size
        self._index = 0
        self._pending = b""
        self._done = False
        self._lookahead: bytes | None = source.read(chunk_size + _TAG_LENGTH)

    def _next_block(self) -> bytes:
        block = self._lookahead
        if block is None:
            return b""
        self._lookahead = self._source.read(self._chunk + _TAG_LENGTH)
        last = not self._lookahead
        if len(block) < _TAG_LENGTH or (not last and len(block) != self._chunk + _TAG_LENGTH):
            msg = "блок шифртекста обрезан"
            raise BackupCryptoError(msg)
        try:
            plain = self._aead.decrypt(_nonce(self._prefix, self._index), block, _aad(self._header, self._index, last))
        except InvalidTag as exc:
            msg = "блок не прошёл проверку: ключ не подходит или данные повреждены"
            raise BackupCryptoError(msg) from exc
        self._index += 1
        if last:
            self._lookahead = None
            self._done = True
        return plain

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            parts = [self._pending]
            self._pending = b""
            while not self._done:
                parts.append(self._next_block())
            return b"".join(parts)
        while len(self._pending) < size and not self._done:
            self._pending += self._next_block()
        out, self._pending = self._pending[:size], self._pending[size:]
        return out

    def readable(self) -> bool:
        return True


def hash_stream(source: BinaryIO, *, on_chunk: Callable[[int], None] | None = None) -> tuple[int, str]:
    """Размер и sha256 потока (шифртекста в хранилище)."""
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(CHUNK_SIZE):
        digest.update(chunk)
        size += len(chunk)
        if on_chunk is not None:
            on_chunk(size)
    return size, digest.hexdigest()
