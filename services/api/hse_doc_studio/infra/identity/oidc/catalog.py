"""Каталог OIDC-провайдеров: один из окружения (HSE_STUDIO__AUTH__OIDC__*) и сколько угодно из таблицы."""

from __future__ import annotations

import logging

from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.identity.oidc import OidcProviderConfig
from hse_doc_studio.core.identity.protocols import IOidcProviderRepository
from hse_doc_studio.core.secrets import column_aad

logger = logging.getLogger(__name__)

_TABLE = "oidc_providers"
_COLUMN = "client_secret_enc"  # noqa: S105 — имя колонки, не секрет


class OidcProviderCatalog:
    """Провайдер из окружения побеждает одноимённого из таблицы: заданное в окружении в админке не правится."""

    def __init__(
        self, repo: IOidcProviderRepository, cipher: ISecretCipher, env: OidcProviderConfig | None = None
    ) -> None:
        self._repo = repo
        self._cipher = cipher
        self._env = env

    async def get(self, provider_id: str) -> OidcProviderConfig | None:
        if self._env is not None and self._env.id == provider_id:
            return self._env
        row = await self._repo.get(provider_id)
        if row is None or not row.enabled:
            return None
        try:
            secret = self._cipher.decrypt(row.client_secret_enc, aad=column_aad(_TABLE, _COLUMN, row.id))
        except GitSyncError:
            # Ключ сменили или запись повреждена: вход через этого провайдера недоступен, остальные работают.
            logger.warning("OIDC provider %s: client secret is unreadable", row.id)
            return None
        return OidcProviderConfig(
            id=row.id,
            label=row.label,
            issuer=row.issuer,
            client_id=row.client_id,
            client_secret=secret.reveal(),
            scopes=row.scopes,
            auto_provision=row.auto_provision,
        )

    async def list_enabled(self) -> list[tuple[str, str]]:
        found: dict[str, str] = {}
        if self._env is not None:
            found[self._env.id] = self._env.label
        for row in await self._repo.list(only_enabled=True):
            found.setdefault(row.id, row.label)
        return list(found.items())
