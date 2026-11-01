from __future__ import annotations

import io
import os

import pytest
from hse_doc_studio.core.backup.crypto import (
    CHUNK_SIZE,
    BackupCryptoError,
    DecryptingReader,
    EncryptingWriter,
    key_check,
    key_from_installation,
    key_from_passphrase,
    key_matches,
    new_salt,
)

KEY = os.urandom(32)


def _seal(data: bytes, key: bytes = KEY, *, chunk: int = CHUNK_SIZE) -> tuple[bytes, EncryptingWriter]:
    sink = io.BytesIO()
    writer = EncryptingWriter(sink, key, chunk_size=chunk)
    for start in range(0, len(data), 7919):
        writer.write(data[start : start + 7919])
    writer.close()
    return sink.getvalue(), writer


def _open(blob: bytes, key: bytes = KEY) -> bytes:
    return DecryptingReader(io.BytesIO(blob), key).read()


@pytest.mark.parametrize("size", [0, 1, 4095, 4096, 4097, 3 * 4096, 10_000])
def test__roundtrip__various_sizes__restores_plaintext(size: int) -> None:
    data = os.urandom(size)
    blob, writer = _seal(data, chunk=4096)
    assert _open(blob) == data
    assert writer.stats.plain_size == size
    assert writer.stats.cipher_size == len(blob)


def test__stats__hashes_match_streams() -> None:
    import hashlib

    data = os.urandom(9000)
    blob, writer = _seal(data, chunk=4096)
    assert writer.stats.plain_sha256 == hashlib.sha256(data).hexdigest()
    assert writer.stats.cipher_sha256 == hashlib.sha256(blob).hexdigest()


def test__ciphertext__does_not_contain_plaintext_and_differs_between_runs() -> None:
    data = "секретные данные проекта".encode() * 50
    first, _ = _seal(data)
    second, _ = _seal(data)
    assert data[:20] not in first
    assert first != second


def test__wrong_key__rejected() -> None:
    blob, _ = _seal(b"x" * 100)
    with pytest.raises(BackupCryptoError):
        _open(blob, os.urandom(32))


def test__flipped_byte__rejected() -> None:
    blob, _ = _seal(os.urandom(5000), chunk=4096)
    broken = bytearray(blob)
    broken[len(broken) // 2] ^= 1
    with pytest.raises(BackupCryptoError):
        _open(bytes(broken))


def test__truncated_at_block_boundary__rejected() -> None:
    blob, _ = _seal(os.urandom(3 * 4096 + 10), chunk=4096)
    header = 6 + 4 + 8
    cut = blob[: header + 2 * (4096 + 16)]
    with pytest.raises(BackupCryptoError):
        _open(cut)


def test__swapped_blocks__rejected() -> None:
    blob, _ = _seal(os.urandom(3 * 4096 + 10), chunk=4096)
    header, body = blob[:18], blob[18:]
    size = 4096 + 16
    swapped = header + body[size : 2 * size] + body[:size] + body[2 * size :]
    with pytest.raises(BackupCryptoError):
        _open(swapped)


def test__foreign_file__rejected() -> None:
    with pytest.raises(BackupCryptoError):
        DecryptingReader(io.BytesIO(b"not a backup at all, definitely"), KEY)
    with pytest.raises(BackupCryptoError):
        DecryptingReader(io.BytesIO(b"short"), KEY)


def test__partial_reads__concatenate_to_plaintext() -> None:
    data = os.urandom(10_000)
    blob, _ = _seal(data, chunk=4096)
    reader = DecryptingReader(io.BytesIO(blob), KEY)
    parts = []
    while chunk := reader.read(1000):
        parts.append(chunk)
    assert b"".join(parts) == data


def test__keys__derivation_is_deterministic_and_salted() -> None:
    raw = os.urandom(32)
    salt = new_salt()
    assert key_from_installation(raw, salt) == key_from_installation(raw, salt)
    assert key_from_installation(raw, salt) != key_from_installation(raw, new_salt())
    assert key_from_passphrase("correct horse battery", salt) == key_from_passphrase("correct horse battery", salt)
    assert key_from_passphrase("correct horse battery", salt) != key_from_passphrase("another phrase here", salt)


def test__key_check__distinguishes_keys_without_revealing_them() -> None:
    a, b = os.urandom(32), os.urandom(32)
    check = key_check(a)
    assert key_matches(a, check)
    assert not key_matches(b, check)
    assert a.hex() not in check
