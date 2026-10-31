"""Postgres-репозиторий входа устройств по коду (device flow)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select, update

from hse_doc_studio.core.git_remote.device import DeviceAuthorization, DeviceClientKind, DeviceStatus
from hse_doc_studio.infra.db.orm.device_auth import DeviceAuthorizationRow
from hse_doc_studio.infra.db.session import SessionProvider


def _item(row: DeviceAuthorizationRow) -> DeviceAuthorization:
    return DeviceAuthorization(
        id=row.id,
        device_code_hash=row.device_code_hash,
        user_code=row.user_code,
        client_name=row.client_name,
        client_kind=DeviceClientKind(row.client_kind),
        requested_scopes=tuple(row.requested_scopes),
        status=DeviceStatus(row.status),
        created_at=row.created_at,
        expires_at=row.expires_at,
        client_ip=row.client_ip,
        granted_scopes=tuple(row.granted_scopes) if row.granted_scopes is not None else None,
        user_id=row.user_id,
        token_id=row.token_id,
        token_secret_enc=row.token_secret_enc,
        decided_at=row.decided_at,
        last_polled_at=row.last_polled_at,
    )


class SqlDeviceAuthorizationRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, item: DeviceAuthorization) -> None:
        async with self._sessions.use() as db:
            db.add(
                DeviceAuthorizationRow(
                    id=item.id,
                    device_code_hash=item.device_code_hash,
                    user_code=item.user_code,
                    client_name=item.client_name,
                    client_kind=item.client_kind.value,
                    requested_scopes=list(item.requested_scopes),
                    granted_scopes=list(item.granted_scopes) if item.granted_scopes is not None else None,
                    client_ip=item.client_ip,
                    status=item.status.value,
                    user_id=item.user_id,
                    token_id=item.token_id,
                    token_secret_enc=item.token_secret_enc,
                    created_at=item.created_at,
                    expires_at=item.expires_at,
                    decided_at=item.decided_at,
                    last_polled_at=item.last_polled_at,
                )
            )
            await db.flush()

    async def _one(self, *where: object) -> DeviceAuthorization | None:
        stmt = select(DeviceAuthorizationRow).where(*where).execution_options(populate_existing=True)  # type: ignore[arg-type]
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _item(row) if row else None

    async def get_by_user_code(self, user_code: str) -> DeviceAuthorization | None:
        return await self._one(DeviceAuthorizationRow.user_code == user_code)

    async def get_by_device_hash(self, device_code_hash: str) -> DeviceAuthorization | None:
        return await self._one(DeviceAuthorizationRow.device_code_hash == device_code_hash)

    async def touch_poll(self, item_id: str, now: datetime) -> None:
        stmt = update(DeviceAuthorizationRow).where(DeviceAuthorizationRow.id == item_id).values(last_polled_at=now)
        async with self._sessions.use() as db:
            await db.execute(stmt)

    async def decide(  # noqa: PLR0913 — поля решения
        self,
        item_id: str,
        status: DeviceStatus,
        *,
        user_id: str,
        now: datetime,
        granted_scopes: tuple[str, ...] | None = None,
        token_id: str | None = None,
        token_secret_enc: str | None = None,
    ) -> bool:
        stmt = (
            update(DeviceAuthorizationRow)
            .where(DeviceAuthorizationRow.id == item_id, DeviceAuthorizationRow.status == DeviceStatus.pending.value)
            .values(
                status=status.value,
                user_id=user_id,
                decided_at=now,
                granted_scopes=list(granted_scopes) if granted_scopes is not None else None,
                token_id=token_id,
                token_secret_enc=token_secret_enc,
            )
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]

    async def deliver(self, item_id: str) -> bool:
        stmt = (
            update(DeviceAuthorizationRow)
            .where(DeviceAuthorizationRow.id == item_id, DeviceAuthorizationRow.status == DeviceStatus.approved.value)
            .values(status=DeviceStatus.delivered.value, token_secret_enc=None)
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]

    async def purge(self, older_than: datetime) -> int:
        stmt = delete(DeviceAuthorizationRow).where(DeviceAuthorizationRow.created_at < older_than)
        async with self._sessions.use() as db:
            return int((await db.execute(stmt)).rowcount)  # type: ignore[attr-defined]
