"""Профиль подписанта: сохранённая картинка подписи и открытая часть ключа для плашки (signing-route.md, срез R10).

Профиль живёт у аккаунта на сервере и годится для любого проекта: подписант ставит ту же картинку и ту же плашку, не
загружая их заново. Закрытой части здесь не бывает: файл с закрытым ключом отвергается до сохранения, а храним мы
только сертификат X.509 или открытый ключ OpenPGP и разобранные из них данные плашки.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.value_objects import SignerInfo

# Нарисованная или очищенная от фона подпись весит десятки килобайт; запас на скан с телефона.
MAX_PROFILE_IMAGE_BYTES = 2 * 1024 * 1024
# Сертификат занимает пару килобайт, открытый ключ OpenPGP с подписями других людей больше.
MAX_PROFILE_KEY_BYTES = 128 * 1024


class PublicKeyKind(StrEnum):
    x509 = "x509"
    openpgp = "openpgp"


@dataclass(frozen=True)
class ProfileImage:
    """Картинка подписи без самих байтов: их отдаёт отдельный вызов репозитория."""

    sha256: str
    size: int
    width_px: int | None
    height_px: int | None
    updated_at: datetime


@dataclass(frozen=True)
class ProfilePublicKey:
    """Сертификат X.509 (PEM) или открытый ключ OpenPGP в том виде, в каком его загрузили, и данные плашки из него."""

    kind: PublicKeyKind
    data: bytes = field(repr=False)
    plate: SignerInfo
    updated_at: datetime


@dataclass(frozen=True)
class SignerProfile:
    user_id: str
    image: ProfileImage | None = None
    public_key: ProfilePublicKey | None = None

    @property
    def empty(self) -> bool:
        return self.image is None and self.public_key is None


class SecretKeyMaterialError(ValueError):
    """В загруженном файле есть закрытый ключ: профиль принимает только открытую часть."""

    def __init__(self) -> None:
        super().__init__(
            localized_error(
                "В файле закрытый ключ. В профиль загружается только открытая часть: сертификат (.cer, .crt, .pem) "
                "или открытый ключ OpenPGP (.asc, gpg --export --armor)",
                "The file holds a private key. The profile takes only the public part: a certificate (.cer, .crt, "
                ".pem) or an OpenPGP public key (.asc, gpg --export --armor)",
            )
        )


@dataclass(frozen=True)
class PublicKeyData:
    """Разобранная открытая часть ключа: что сохранить и что напечатать на плашке."""

    kind: PublicKeyKind
    # Сертификат перепакован в PEM без остального содержимого файла; ключ OpenPGP хранится как загружен.
    data: bytes = field(repr=False)
    plate: SignerInfo


class IPublicKeyReader(Protocol):
    async def read(self, blob: bytes) -> PublicKeyData:
        """Сертификат X.509 или открытый ключ OpenPGP из файла, ничего не сохраняя и не импортируя.

        Файл с закрытым ключом в любом виде: `SecretKeyMaterialError`; не ключ и не сертификат: `ValueError`.
        """
        ...


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def png_size(blob: bytes) -> tuple[int, int] | None:
    """Ширина и высота PNG из заголовка IHDR; None, если это не PNG."""
    if len(blob) < 24 or blob[:8] != _PNG_MAGIC or blob[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", blob[16:24])
    return int(width), int(height)


class ISignerProfileRepository(Protocol):
    """Профили подписантов по id пользователя.

    Репозиторий не проверяет, чей профиль читают: свой профиль меняют и смотрят только сценарии владельца (актор из
    запроса), а маршрут подписания читает у участника только открытую часть для плашки.
    """

    async def get(self, user_id: str) -> SignerProfile:
        """Профиль без байтов картинки; у человека без профиля пустой профиль."""
        ...

    async def read_image(self, user_id: str) -> bytes | None: ...

    async def save_image(self, user_id: str, png: bytes, image: ProfileImage) -> None: ...

    async def clear_image(self, user_id: str) -> bool:
        """False, если картинки не было."""
        ...

    async def save_public_key(self, user_id: str, key: ProfilePublicKey) -> None: ...

    async def clear_public_key(self, user_id: str) -> bool:
        """False, если ключа не было."""
        ...
