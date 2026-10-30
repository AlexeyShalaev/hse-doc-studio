"""Postgres-репозиторий сопряжений по коду устройства."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update

from hse_doc_studio.core.jobs.pairing import PairingStatus, RunnerPairing
from hse_doc_studio.core.jobs.runners import RunnerHostKind
from hse_doc_studio.infra.db.orm.jobs import RunnerPairingRow
from hse_doc_studio.infra.db.session import SessionProvider


def _pairing(row: RunnerPairingRow) -> RunnerPairing:
    return RunnerPairing(
        id=row.id,
        device_code_hash=row.device_code_hash,
        user_code=row.user_code,
        name=row.name,
        host_kind=RunnerHostKind(row.host_kind),
        client_ip=row.client_ip,
        status=PairingStatus(row.status),
        created_at=row.created_at,
        expires_at=row.expires_at,
        user_id=row.user_id,
        token_id=row.token_id,
        token_secret_enc=row.token_secret_enc,
        decided_at=row.decided_at,
    )


class SqlRunnerPairingRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, pairing: RunnerPairing) -> None:
        async with self._sessions.use() as db:
            db.add(
                RunnerPairingRow(
                    id=pairing.id,
                    device_code_hash=pairing.device_code_hash,
                    user_code=pairing.user_code,
                    name=pairing.name,
                    host_kind=pairing.host_kind.value,
                    client_ip=pairing.client_ip,
                    status=pairing.status.value,
                    user_id=pairing.user_id,
                    token_id=pairing.token_id,
                    token_secret_enc=pairing.token_secret_enc,
                    created_at=pairing.created_at,
                    expires_at=pairing.expires_at,
                    decided_at=pairing.decided_at,
                )
            )
            await db.flush()

    async def _one(self, *where: object) -> RunnerPairing | None:
        async with self._sessions.use() as db:
            row = (
                await db.execute(select(RunnerPairingRow).where(*where).execution_options(populate_existing=True))  # type: ignore[arg-type]
            ).scalar_one_or_none()
            return _pairing(row) if row else None

    async def get_by_user_code(self, user_code: str) -> RunnerPairing | None:
        return await self._one(RunnerPairingRow.user_code == user_code)

    async def get_by_device_hash(self, device_code_hash: str) -> RunnerPairing | None:
        return await self._one(RunnerPairingRow.device_code_hash == device_code_hash)

    async def decide(
        self,
        pairing_id: str,
        status: PairingStatus,
        *,
        user_id: str,
        now: datetime,
        token_id: str | None = None,
        token_secret_enc: str | None = None,
    ) -> bool:
        stmt = (
            update(RunnerPairingRow)
            .where(RunnerPairingRow.id == pairing_id, RunnerPairingRow.status == PairingStatus.pending.value)
            .values(
                status=status.value,
                user_id=user_id,
                decided_at=now,
                token_id=token_id,
                token_secret_enc=token_secret_enc,
            )
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]

    async def deliver(self, pairing_id: str) -> bool:
        stmt = (
            update(RunnerPairingRow)
            .where(RunnerPairingRow.id == pairing_id, RunnerPairingRow.status == PairingStatus.approved.value)
            .values(status=PairingStatus.delivered.value, token_secret_enc=None)
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]

    async def purge(self, older_than: datetime) -> int:
        stmt = delete(RunnerPairingRow).where(RunnerPairingRow.created_at < older_than)
        async with self._sessions.use() as db:
            return int((await db.execute(stmt)).rowcount)  # type: ignore[attr-defined]
