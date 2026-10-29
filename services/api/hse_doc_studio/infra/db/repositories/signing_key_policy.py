"""Политика хранения закрытых ключей: значение `signing.server_key_storage` в instance_settings, по умолчанию запрет."""

from __future__ import annotations

from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.signatures.key_policy import SERVER_KEY_STORAGE_SETTING


class InstanceSigningKeyPolicy:
    def __init__(self, settings: IInstanceSettingsRepository) -> None:
        self._settings = settings

    async def server_key_storage_allowed(self) -> bool:
        return (await self._settings.get_all()).get(SERVER_KEY_STORAGE_SETTING) is True
