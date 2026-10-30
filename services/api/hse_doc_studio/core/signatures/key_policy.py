"""Политика серверных ключей подписи установки: разрешены ли закрытые ключи, которые хранит сервер."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.i18n import localized_error

KEY_SERVER_KEYS = "signing.server_key_storage"
SERVER_KEY_STORAGE_SETTING = KEY_SERVER_KEYS


class ServerKeyPolicy(StrEnum):
    allowed = "allowed"
    forbidden = "forbidden"


def server_key_policy_from(values: Mapping[str, object]) -> ServerKeyPolicy:
    """Без записи или с непонятной записью ключи на сервере запрещены."""
    raw = values.get(KEY_SERVER_KEYS)
    try:
        return ServerKeyPolicy(raw) if isinstance(raw, str) else ServerKeyPolicy.forbidden
    except ValueError:
        return ServerKeyPolicy.forbidden


class SigningKeyStorageDeniedError(ValueError):
    """Админ установки не разрешил хранить закрытые ключи подписи на сервере."""

    def __init__(self) -> None:
        super().__init__(
            localized_error(
                "Администратор запретил хранить закрытые ключи подписи на сервере. "
                "Загрузите готовую подпись или подпишите файл в КриптоПро в браузере",
                "The administrator has forbidden storing private signing keys on the server. "
                "Upload a ready signature or sign the file with CryptoPro in the browser",
            )
        )


class ISigningKeyPolicy(Protocol):
    async def server_key_storage_allowed(self) -> bool:
        """Можно ли сохранять закрытый ключ в БД сервера. По умолчанию нет."""
        ...
