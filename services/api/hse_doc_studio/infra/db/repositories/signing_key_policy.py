"""Политика хранения закрытых ключей: `signing.server_key_storage` (allowed|forbidden), по умолчанию запрет."""

from __future__ import annotations

from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.signatures.key_policy import ServerKeyPolicy, server_key_policy_from


class InstanceSigningKeyPolicy:
    def __init__(self, settings: IInstanceSettingsRepository) -> None:
        self._settings = settings

    async def server_key_storage_allowed(self) -> bool:
        return server_key_policy_from(await self._settings.get_all()) is ServerKeyPolicy.allowed
