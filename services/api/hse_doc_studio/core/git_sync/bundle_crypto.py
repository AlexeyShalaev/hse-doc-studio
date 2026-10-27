"""Контейнер HSEB1: переносной файл проекта под паролем.

Файл бывает большим, поэтому шифруется кадрами: каждый кадр это отдельный токен Fernet с куском данных. Ключ
выводится из пароля тем же PBKDF2, что и в зашифрованных настройках (`core.export_import.encryption`), соль
своя на файл.

    HSEB1 | соль (16 байт) | кадр | кадр | ...
    кадр = длина токена (4 байта, big-endian) | токен Fernet
    содержимое токена = признак последнего кадра (1 байт) | номер кадра (4 байта) | данные

Признак и номер лежат внутри токена, под его подписью: обрезанный файл (нет последнего кадра), переставленные
или вставленные кадры не пройдут проверку. Неверный пароль виден уже на первом кадре.
"""

from __future__ import annotations

import struct
from enum import StrEnum
from typing import BinaryIO, Final

from cryptography.fernet import Fernet, InvalidToken

from hse_doc_studio.core.export_import.encryption import SALT_LENGTH, derive_key

MAGIC: Final = b"HSEB1"
CHUNK_BYTES: Final = 4 * 1024 * 1024
# Токен Fernet на кадр в четыре мегабайта занимает около 5,6 МБ; больше этого кадр быть не может.
MAX_FRAME_BYTES: Final = 8 * 1024 * 1024
_LENGTH: Final = struct.Struct(">I")
_META: Final = struct.Struct(">BI")
_MORE: Final = 0
_LAST: Final = 1

_PLAIN_MAGIC: Final = (b"# v2 git bundle\n", b"# v3 git bundle\n")
# Сколько байт файла нужно, чтобы узнать его вид.
SNIFF_BYTES: Final = 32


class BundleFormat(StrEnum):
    plain = "plain"
    encrypted = "encrypted"
    unknown = "unknown"


class BundleCryptoError(Exception):
    """Контейнер нельзя прочитать: повреждён, обрезан или это не он."""


class WrongPasswordError(BundleCryptoError):
    """Первый кадр не открылся ключом из этого пароля."""


def sniff(head: bytes) -> BundleFormat:
    """Вид файла по его началу."""
    if head.startswith(MAGIC):
        return BundleFormat.encrypted
    if head.startswith(_PLAIN_MAGIC):
        return BundleFormat.plain
    return BundleFormat.unknown


def encrypt_stream(source: BinaryIO, target: BinaryIO, password: str, *, salt: bytes) -> None:
    """Шифрует `source` целиком в `target`. Соль передаёт вызывающий (`os.urandom`), чтобы функция была чистой."""
    if len(salt) != SALT_LENGTH:
        raise ValueError("salt has a wrong length")
    fernet = Fernet(derive_key(password, salt))
    target.write(MAGIC + salt)
    index = 0
    chunk = source.read(CHUNK_BYTES)
    while True:
        following = source.read(CHUNK_BYTES) if len(chunk) == CHUNK_BYTES else b""
        token = fernet.encrypt(_META.pack(_LAST if not following else _MORE, index) + chunk)
        target.write(_LENGTH.pack(len(token)) + token)
        if not following:
            return
        chunk, index = following, index + 1


def decrypt_stream(source: BinaryIO, target: BinaryIO, password: str) -> None:
    """Расшифровывает контейнер. Бросает WrongPasswordError или BundleCryptoError."""
    fernet = _open(source, password)
    index = 0
    while True:
        last, data = _read_frame(source, fernet, index)
        target.write(data)
        if last:
            if source.read(1):
                raise BundleCryptoError("data after the last frame")
            return
        index += 1


def check_password(source: BinaryIO, password: str) -> None:
    """Открывает только заголовок и первый кадр: хватает, чтобы отличить неверный пароль от повреждённого файла."""
    _read_frame(source, _open(source, password), 0)


def _open(source: BinaryIO, password: str) -> Fernet:
    header = source.read(len(MAGIC) + SALT_LENGTH)
    if len(header) != len(MAGIC) + SALT_LENGTH or not header.startswith(MAGIC):
        raise BundleCryptoError("not a bundle container")
    return Fernet(derive_key(password, header[len(MAGIC) :]))


def _read_frame(source: BinaryIO, fernet: Fernet, index: int) -> tuple[bool, bytes]:
    token = _read_token(source)
    try:
        plain = fernet.decrypt(token)
    except InvalidToken:
        if index == 0:
            raise WrongPasswordError("the password does not open the container") from None
        raise BundleCryptoError("a frame is damaged") from None
    if len(plain) < _META.size:
        raise BundleCryptoError("a frame is too short")
    flag, number = _META.unpack(plain[: _META.size])
    if number != index or flag not in (_MORE, _LAST):
        raise BundleCryptoError("frames are out of order")
    return flag == _LAST, plain[_META.size :]


def _read_token(source: BinaryIO) -> bytes:
    prefix = source.read(_LENGTH.size)
    if len(prefix) != _LENGTH.size:
        raise BundleCryptoError("the container is truncated")
    (size,) = _LENGTH.unpack(prefix)
    if size == 0 or size > MAX_FRAME_BYTES:
        raise BundleCryptoError("a frame has a wrong size")
    token = source.read(size)
    if len(token) != size:
        raise BundleCryptoError("the container is truncated")
    return token
