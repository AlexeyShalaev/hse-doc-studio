"""Политика хранения закрытых ключей: `signing.server_key_storage` (allowed|forbidden), по умолчанию запрет."""

from __future__ import annotations

from sqlalchemy import func, select

from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.signatures.key_policy import ServerKeyPolicy, server_key_policy_from
from hse_doc_studio.infra.db.orm.signing_identities import SigningIdentityRow
from hse_doc_studio.infra.db.session import SessionProvider


class InstanceSigningKeyPolicy:
    def __init__(self, settings: IInstanceSettingsRepository) -> None:
        self._settings = settings

    async def server_key_storage_allowed(self) -> bool:
        return server_key_policy_from(await self._settings.get_all()) is ServerKeyPolicy.allowed


class SqlServerKeyCounter:
    """Сколько закрытых ключей подписи лежит в базе у всех людей, для экрана политики в админке."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def count_server_keys(self) -> int:
        stmt = select(func.count()).select_from(SigningIdentityRow).where(SigningIdentityRow.key_enc.is_not(None))
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())
