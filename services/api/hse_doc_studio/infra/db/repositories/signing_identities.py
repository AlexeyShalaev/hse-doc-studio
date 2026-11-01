"""Идентичности подписи в Postgres: видит и меняет только владелец, закрытый ключ шифртекстом по разрешению админа."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, select

from hse_doc_studio.core.access.context import ActorRequired, require_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.entities import SigningIdentity, SigningKeyMaterial
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.signatures.key_policy import ISigningKeyPolicy, SigningKeyStorageDeniedError
from hse_doc_studio.infra.db.orm.signing_identities import SigningIdentityRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.signatures.key_session import key_directory


class PostgresSigningIdentityRepository:
    """ISigningIdentityRepository сервера.

    Чужая идентичность неотличима от несуществующей. Закрытый ключ сохраняется только если политика установки
    это разрешает, лежит шифртекстом с привязкой к таблице, колонке и id и расшифровывается лишь в
    `private_key_session`: во временный каталог 0700, который затирается на выходе.
    """

    def __init__(
        self,
        sessions: SessionProvider,
        cipher: ISecretCipher,
        policy: ISigningKeyPolicy,
        *,
        tmp_root: Path | None = None,
    ) -> None:
        self._sessions = sessions
        self._cipher = cipher
        self._policy = policy
        self._tmp_root = tmp_root

    async def list_all(self) -> list[SigningIdentity]:
        owner = _owner_id()
        stmt = (
            select(SigningIdentityRow)
            .where(SigningIdentityRow.owner_id == owner)
            .order_by(SigningIdentityRow.created_at, SigningIdentityRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_entity(row) for row in rows]

    async def get(self, identity_id: UUID) -> SigningIdentity | None:
        row = await self._row(identity_id)
        return None if row is None else _to_entity(row)

    async def create(self, identity: SigningIdentity, material: SigningKeyMaterial | None = None) -> None:
        owner = _owner_id()
        key_enc: str | None = None
        cert_pem: str | None = None
        if material is not None:
            if not await self._policy.server_key_storage_allowed():
                raise SigningKeyStorageDeniedError
            key_enc = self._cipher.encrypt(
                Secret(material.key_pem.decode("ascii")), aad=column_aad("signing_identities", "key_enc", identity.id)
            )
            cert_pem = material.cert_pem.decode("ascii")
        async with self._sessions.use() as session:
            session.add(
                SigningIdentityRow(
                    id=identity.id,
                    owner_id=owner,
                    label=identity.label,
                    kind=identity.kind.value,
                    subject_cn=identity.subject_cn,
                    not_after=identity.not_after,
                    trusted=identity.trusted,
                    fingerprint=identity.fingerprint,
                    protected=identity.protected,
                    cert_pem=cert_pem,
                    key_enc=key_enc,
                    created_at=identity.created_at,
                )
            )

    async def delete(self, identity_id: UUID) -> bool:
        owner = _owner_id()
        async with self._sessions.use() as session:
            result = await session.execute(
                delete(SigningIdentityRow)
                .where(SigningIdentityRow.id == identity_id, SigningIdentityRow.owner_id == owner)
                .returning(SigningIdentityRow.id)
            )
            return result.first() is not None

    async def read_cert(self, identity_id: UUID) -> bytes | None:
        row = await self._row(identity_id)
        return None if row is None or row.cert_pem is None else row.cert_pem.encode("ascii")

    @contextlib.asynccontextmanager
    async def private_key_session(self, identity_id: UUID) -> AsyncIterator[Path]:
        row = await self._row(identity_id)
        if row is None:
            raise NotFoundError(
                localized_error(
                    f"Учётная запись подписи {identity_id} не найдена", f"Signing identity {identity_id} not found"
                )
            )
        if row.key_enc is None:
            raise ValueError(
                localized_error(
                    "Закрытый ключ не хранится на сервере: подпишите файл в КриптоПро и загрузите подпись",
                    "The private key is not stored on the server: sign the file in CryptoPro and upload the signature",
                )
            )
        key_pem = (
            self._cipher.decrypt(row.key_enc, aad=column_aad("signing_identities", "key_enc", row.id))
            .reveal()
            .encode("ascii")
        )
        cert_pem = None if row.cert_pem is None else row.cert_pem.encode("ascii")
        with key_directory(key_pem, cert_pem, root=self._tmp_root) as directory:
            yield directory

    async def _row(self, identity_id: UUID) -> SigningIdentityRow | None:
        owner = _owner_id()
        async with self._sessions.use() as session:
            return (
                await session.execute(
                    select(SigningIdentityRow).where(
                        SigningIdentityRow.id == identity_id, SigningIdentityRow.owner_id == owner
                    )
                )
            ).scalar_one_or_none()


def _owner_id() -> str:
    actor = require_actor()
    if actor.kind is not ActorKind.user or actor.id is None:
        raise ActorRequired("ключи подписи доступны только пользователю")
    return actor.id


def _to_entity(row: SigningIdentityRow) -> SigningIdentity:
    return SigningIdentity(
        id=row.id,
        label=row.label,
        kind=SigningIdentityKind(row.kind),
        subject_cn=row.subject_cn,
        not_after=row.not_after,
        trusted=row.trusted,
        created_at=row.created_at,
        fingerprint=row.fingerprint,
        protected=row.protected,
    )
