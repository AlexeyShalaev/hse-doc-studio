"""Политика хранения закрытых ключей: `signing.server_key_storage` (allowed|forbidden), по умолчанию запрет."""

from __future__ import annotations

from sqlalchemy import func, or_, select

from hse_doc_studio.core.enums import SigningIdentityKind
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
    """Сколько закрытых ключей подписи хранит сервер у всех людей, для экрана политики в админке.

    PKCS#12 и самоподписанные лежат шифртекстом в `key_enc`. Закрытый ключ OpenPGP лежит в общей связке на томе
    данных, а у записи `key_enc` пуст; запись OpenPGP появляется только для ключа с секретной частью в связке,
    поэтому каждая такая запись тоже ключ на сервере.
    """

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def count_server_keys(self) -> int:
        stmt = (
            select(func.count())
            .select_from(SigningIdentityRow)
            .where(
                or_(
                    SigningIdentityRow.key_enc.is_not(None),
                    SigningIdentityRow.kind == SigningIdentityKind.openpgp.value,
                )
            )
        )
        async with self._sessions.use() as session:
            return int((await session.execute(stmt)).scalar_one())
