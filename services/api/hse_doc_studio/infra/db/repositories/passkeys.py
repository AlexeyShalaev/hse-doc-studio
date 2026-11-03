"""Postgres-репозиторий ключей passkey."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.identity.passkeys import Passkey, PasskeyFailure, PasskeyVerificationError
from hse_doc_studio.infra.db.orm.passkeys import PasskeyRow
from hse_doc_studio.infra.db.session import SessionProvider


def _passkey(row: PasskeyRow) -> Passkey:
    return Passkey(
        id=row.id,
        user_id=row.user_id,
        credential_id=row.credential_id,
        public_key=bytes(row.public_key),
        sign_count=row.sign_count,
        rp_id=row.rp_id,
        name=row.name,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        transports=tuple(row.transports),
        aaguid=row.aaguid,
        backup_eligible=row.backup_eligible,
        backed_up=row.backed_up,
    )


class SqlPasskeyRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, passkey: Passkey) -> None:
        # ON CONFLICT вместо перехвата IntegrityError: повтор ключа не ломает внешнюю транзакцию.
        stmt = (
            pg_insert(PasskeyRow)
            .values(
                id=passkey.id,
                user_id=passkey.user_id,
                credential_id=passkey.credential_id,
                public_key=passkey.public_key,
                sign_count=passkey.sign_count,
                rp_id=passkey.rp_id,
                name=passkey.name,
                transports=list(passkey.transports),
                aaguid=passkey.aaguid,
                backup_eligible=passkey.backup_eligible,
                backed_up=passkey.backed_up,
                created_at=passkey.created_at,
                last_used_at=passkey.last_used_at,
            )
            .on_conflict_do_nothing(index_elements=[PasskeyRow.credential_id])
            .returning(PasskeyRow.id)
        )
        async with self._sessions.use() as db:
            if (await db.execute(stmt)).scalar_one_or_none() is None:
                raise PasskeyVerificationError(PasskeyFailure.duplicate)

    async def get_by_credential_id(self, credential_id: str) -> Passkey | None:
        stmt = select(PasskeyRow).where(PasskeyRow.credential_id == credential_id)
        async with self._sessions.use() as db:
            row = (await db.execute(stmt.execution_options(populate_existing=True))).scalar_one_or_none()
            return _passkey(row) if row else None

    async def list_for_user(self, user_id: str) -> list[Passkey]:
        stmt = select(PasskeyRow).where(PasskeyRow.user_id == user_id).order_by(PasskeyRow.created_at, PasskeyRow.id)
        async with self._sessions.use() as db:
            return [_passkey(row) for row in (await db.execute(stmt)).scalars()]

    async def count_for_user(self, user_id: str) -> int:
        stmt = select(func.count()).select_from(PasskeyRow).where(PasskeyRow.user_id == user_id)
        async with self._sessions.use() as db:
            return int((await db.execute(stmt)).scalar_one())

    async def rename(self, user_id: str, passkey_id: str, name: str) -> Passkey | None:
        stmt = (
            update(PasskeyRow)
            .where(PasskeyRow.id == passkey_id, PasskeyRow.user_id == user_id)
            .values(name=name)
            .returning(PasskeyRow)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt.execution_options(populate_existing=True))).scalar_one_or_none()
            return _passkey(row) if row else None

    async def delete(self, user_id: str, passkey_id: str) -> bool:
        stmt = delete(PasskeyRow).where(PasskeyRow.id == passkey_id, PasskeyRow.user_id == user_id)
        async with self._sessions.use() as db:
            return bool((await db.execute(stmt)).rowcount)  # type: ignore[attr-defined]

    async def delete_for_user(self, user_id: str) -> int:
        async with self._sessions.use() as db:
            return int((await db.execute(delete(PasskeyRow).where(PasskeyRow.user_id == user_id))).rowcount)  # type: ignore[attr-defined]

    async def record_use(self, passkey_id: str, *, sign_count: int, backed_up: bool, now: datetime) -> None:
        stmt = (
            update(PasskeyRow)
            .where(PasskeyRow.id == passkey_id)
            .values(sign_count=sign_count, backed_up=backed_up, last_used_at=now)
        )
        async with self._sessions.use() as db:
            await db.execute(stmt)

    async def count_by_rp_id(self) -> dict[str, int]:
        stmt = select(PasskeyRow.rp_id, func.count()).group_by(PasskeyRow.rp_id)
        async with self._sessions.use() as db:
            return {rp_id: int(n) for rp_id, n in (await db.execute(stmt)).all()}
