"""Политика хранения закрытых ключей подписи на сервере."""

from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.i18n import localized_error

SERVER_KEY_STORAGE_SETTING = "signing.server_key_storage"


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
