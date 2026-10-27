from __future__ import annotations

import io
import struct

import pytest
from hse_doc_studio.core.git_sync import bundle_crypto
from hse_doc_studio.core.git_sync.bundle_crypto import (
    MAGIC,
    BundleCryptoError,
    BundleFormat,
    WrongPasswordError,
    check_password,
    decrypt_stream,
    encrypt_stream,
    sniff,
)

pytestmark = pytest.mark.unit

_SALT = bytes(range(16))
_PASSWORD = "correct horse"
_CHUNK = 16


@pytest.fixture(autouse=True)
def small_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Кадры по 16 байт: границы кадров проверяются на коротких данных, без мегабайтов."""
    monkeypatch.setattr(bundle_crypto, "CHUNK_BYTES", _CHUNK)


def _seal(data: bytes, password: str = _PASSWORD) -> bytes:
    out = io.BytesIO()
    encrypt_stream(io.BytesIO(data), out, password, salt=_SALT)
    return out.getvalue()


def _open(blob: bytes, password: str = _PASSWORD) -> bytes:
    out = io.BytesIO()
    decrypt_stream(io.BytesIO(blob), out, password)
    return out.getvalue()


def _frames(blob: bytes) -> list[bytes]:
    """Кадры контейнера вместе с длиной."""
    position, frames = len(MAGIC) + len(_SALT), []
    while position < len(blob):
        (size,) = struct.unpack(">I", blob[position : position + 4])
        frames.append(blob[position : position + 4 + size])
        position += 4 + size
    return frames


@pytest.mark.parametrize("size", [0, 1, _CHUNK - 1, _CHUNK, _CHUNK + 1, 2 * _CHUNK, 2 * _CHUNK + 5, 10 * _CHUNK])
def test__round_trip__any_size_across_frame_boundaries(size: int) -> None:
    data = bytes(i % 251 for i in range(size))

    assert _open(_seal(data)) == data


def test__seal__starts_with_magic_and_salt() -> None:
    blob = _seal(b"data")

    assert blob.startswith(MAGIC + _SALT)
    assert sniff(blob[:32]) is BundleFormat.encrypted


def test__seal__same_data_different_password__different_bytes() -> None:
    assert _seal(b"x" * 40) != _seal(b"x" * 40, "other")


def test__seal__empty_input__is_one_final_frame() -> None:
    assert len(_frames(_seal(b""))) == 1


def test__seal__data_of_exactly_one_chunk__is_one_frame() -> None:
    assert len(_frames(_seal(b"a" * _CHUNK))) == 1
    assert len(_frames(_seal(b"a" * (_CHUNK + 1)))) == 2


def test__seal__wrong_salt_length__is_refused() -> None:
    with pytest.raises(ValueError, match="salt"):
        encrypt_stream(io.BytesIO(b"x"), io.BytesIO(), _PASSWORD, salt=b"short")


def test__open__wrong_password__is_told_apart_from_damage() -> None:
    with pytest.raises(WrongPasswordError):
        _open(_seal(b"secret data" * 10), "not it")


def test__check_password__reads_only_the_first_frame() -> None:
    blob = _seal(b"x" * (5 * _CHUNK))
    damaged_tail = blob[: -(len(_frames(blob)[-1]))] + b"\x00\x00\x00\x05junk!"

    check_password(io.BytesIO(damaged_tail), _PASSWORD)
    with pytest.raises(WrongPasswordError):
        check_password(io.BytesIO(damaged_tail), "nope")


def test__open__truncated_at_a_frame_boundary__is_damaged() -> None:
    blob = _seal(b"x" * (3 * _CHUNK))
    frames = _frames(blob)

    with pytest.raises(BundleCryptoError, match="truncated"):
        _open(blob[: len(blob) - len(frames[-1])])


def test__open__truncated_inside_a_frame__is_damaged() -> None:
    with pytest.raises(BundleCryptoError, match="truncated"):
        _open(_seal(b"x" * (3 * _CHUNK))[:-5])


def test__open__frames_swapped__is_damaged() -> None:
    blob = _seal(b"x" * (3 * _CHUNK))
    head = blob[: len(MAGIC) + len(_SALT)]
    frames = _frames(blob)

    with pytest.raises(BundleCryptoError, match="order"):
        _open(head + frames[1] + frames[0] + b"".join(frames[2:]))


def test__open__flipped_byte_in_a_later_frame__is_damaged_not_wrong_password() -> None:
    blob = bytearray(_seal(b"x" * (3 * _CHUNK)))
    blob[-10] ^= 0xFF

    with pytest.raises(BundleCryptoError) as caught:
        _open(bytes(blob))
    assert not isinstance(caught.value, WrongPasswordError)


def test__open__data_after_the_last_frame__is_damaged() -> None:
    with pytest.raises(BundleCryptoError, match="after the last"):
        _open(_seal(b"abc") + b"x")


def test__open__oversized_frame_length__is_damaged_without_reading_it() -> None:
    blob = MAGIC + _SALT + struct.pack(">I", bundle_crypto.MAX_FRAME_BYTES + 1)

    with pytest.raises(BundleCryptoError, match="size"):
        _open(blob)


def test__open__not_a_container__is_damaged() -> None:
    with pytest.raises(BundleCryptoError, match="not a bundle"):
        _open(b"# v2 git bundle\n")


def test__sniff__recognises_plain_bundles_and_rejects_the_rest() -> None:
    assert sniff(b"# v2 git bundle\nabc") is BundleFormat.plain
    assert sniff(b"# v3 git bundle\n@object-format=sha1\n") is BundleFormat.plain
    assert sniff(b"PK\x03\x04") is BundleFormat.unknown
    assert sniff(b"") is BundleFormat.unknown
