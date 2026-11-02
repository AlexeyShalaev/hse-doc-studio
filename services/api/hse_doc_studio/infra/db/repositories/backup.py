"""Назначения и запуски бэкапов в Postgres."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.backup.entities import (
    BackupDestination,
    BackupRun,
    DestinationKind,
    DestinationSpec,
    RunStats,
    RunStatus,
    RunTrigger,
    StoredDestination,
)
from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.infra.db.orm.backup import BackupDestinationRow, BackupRunRow
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.session import SessionProvider


def _stored(row: BackupDestinationRow) -> StoredDestination:
    spec = DestinationSpec(
        name=row.name,
        kind=DestinationKind(row.kind),
        endpoint=row.endpoint,
        region=row.region,
        bucket=row.bucket,
        prefix=row.prefix,
        path_style=row.path_style,
        local_path=row.local_path,
    )
    destination = BackupDestination(
        id=str(row.id),
        spec=spec,
        is_default=row.is_default,
        access_key_hint=row.access_key_hint,
        secret_key_set=row.secret_key_enc is not None,
        created_at=row.created_at,
        updated_at=row.updated_at,
        last_check_at=row.last_check_at,
        last_check_ok=row.last_check_ok,
        last_check_error=row.last_check_error,
    )
    return StoredDestination(destination, row.access_key_enc, row.secret_key_enc)


def _values(stored: StoredDestination) -> dict[str, object]:
    d, spec = stored.destination, stored.destination.spec
    return {
        "name": spec.name,
        "kind": spec.kind.value,
        "endpoint": spec.endpoint,
        "region": spec.region,
        "bucket": spec.bucket,
        "prefix": spec.prefix,
        "path_style": spec.path_style,
        "local_path": spec.local_path,
        "access_key_enc": stored.access_key_enc,
        "secret_key_enc": stored.secret_key_enc,
        "access_key_hint": d.access_key_hint,
        "updated_at": d.updated_at,
        "last_check_at": d.last_check_at,
        "last_check_ok": d.last_check_ok,
        "last_check_error": d.last_check_error,
    }


def _run(row: BackupRunRow) -> BackupRun:
    return BackupRun(
        id=str(row.id),
        destination_id=str(row.destination_id) if row.destination_id else None,
        destination_name=row.destination_name,
        trigger=RunTrigger(row.trigger),
        status=RunStatus(row.status),
        stage=row.stage,
        started_at=row.started_at,
        started_by=row.started_by,
        finished_at=row.finished_at,
        size_bytes=row.size_bytes,
        backup_id=row.backup_id,
        error=row.error,
        manifest_sha256=row.manifest_sha256,
        removed_at=row.removed_at,
    )


class SqlBackupDestinationRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def list_all(self) -> list[BackupDestination]:
        stmt = select(BackupDestinationRow).order_by(BackupDestinationRow.created_at, BackupDestinationRow.id)
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_stored(row).destination for row in rows]

    async def get(self, destination_id: str) -> StoredDestination | None:
        async with self._sessions.use() as session:
            row = await session.get(BackupDestinationRow, UUID(destination_id))
        return _stored(row) if row else None

    async def get_default(self) -> StoredDestination | None:
        stmt = select(BackupDestinationRow).where(BackupDestinationRow.is_default.is_(True))
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _stored(row) if row else None

    async def add(self, stored: StoredDestination) -> None:
        async with self._sessions.use() as session:
            total = (await session.execute(select(func.count()).select_from(BackupDestinationRow))).scalar_one()
            row = BackupDestinationRow(
                id=UUID(stored.destination.id),
                created_at=stored.destination.created_at,
                is_default=total == 0,
                **_values(stored),
            )
            session.add(row)
            await session.flush()

    async def update(self, stored: StoredDestination) -> None:
        async with self._sessions.use() as session:
            await session.execute(
                update(BackupDestinationRow)
                .where(BackupDestinationRow.id == UUID(stored.destination.id))
                .values(**_values(stored))
            )

    async def delete(self, destination_id: str) -> None:
        dest = UUID(destination_id)
        async with self._sessions.use() as session:
            row = await session.get(BackupDestinationRow, dest)
            if row is None:
                return
            was_default = row.is_default
            await session.execute(delete(BackupDestinationRow).where(BackupDestinationRow.id == dest))
            if was_default:
                heir = (
                    await session.execute(
                        select(BackupDestinationRow.id)
                        .order_by(BackupDestinationRow.created_at, BackupDestinationRow.id)
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if heir is not None:
                    await session.execute(
                        update(BackupDestinationRow).where(BackupDestinationRow.id == heir).values(is_default=True)
                    )

    async def set_default(self, destination_id: str) -> None:
        dest = UUID(destination_id)
        async with self._sessions.use() as session:
            # Сначала снимаем метку: частичный уникальный индекс не допускает двух умолчаний даже на миг.
            await session.execute(
                update(BackupDestinationRow).where(BackupDestinationRow.is_default.is_(True)).values(is_default=False)
            )
            await session.execute(
                update(BackupDestinationRow).where(BackupDestinationRow.id == dest).values(is_default=True)
            )

    async def record_check(self, destination_id: str, *, at: datetime, ok: bool, error: str | None) -> None:
        async with self._sessions.use() as session:
            await session.execute(
                update(BackupDestinationRow)
                .where(BackupDestinationRow.id == UUID(destination_id))
                .values(last_check_at=at, last_check_ok=ok, last_check_error=error)
            )

    async def name_taken(self, name: str, *, except_id: str | None = None) -> bool:
        stmt = (
            select(func.count())
            .select_from(BackupDestinationRow)
            .where(func.lower(BackupDestinationRow.name) == name.strip().lower())
        )
        if except_id:
            stmt = stmt.where(BackupDestinationRow.id != UUID(except_id))
        async with self._sessions.use() as session:
            return (await session.execute(stmt)).scalar_one() > 0


class SqlBackupRunRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def start(self, run: BackupRun) -> bool:
        stmt = (
            pg_insert(BackupRunRow)
            .values(
                id=UUID(run.id),
                destination_id=UUID(run.destination_id) if run.destination_id else None,
                destination_name=run.destination_name,
                trigger=run.trigger.value,
                started_by=run.started_by,
                status=RunStatus.running.value,
                stage=run.stage,
                started_at=run.started_at,
            )
            .on_conflict_do_nothing()
        )
        async with self._sessions.use() as session:
            result = await session.execute(stmt)
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def set_stage(self, run_id: str, stage: str) -> None:
        async with self._sessions.use() as session:
            await session.execute(update(BackupRunRow).where(BackupRunRow.id == UUID(run_id)).values(stage=stage))

    async def finish(
        self,
        run_id: str,
        *,
        status: RunStatus,
        at: datetime,
        size_bytes: int | None,
        backup_id: str | None,
        error: str | None,
        manifest_sha256: str | None,
    ) -> BackupRun:
        async with self._sessions.use() as session:
            await session.execute(
                update(BackupRunRow)
                .where(BackupRunRow.id == UUID(run_id))
                .values(
                    status=status.value,
                    stage=None,
                    finished_at=at,
                    size_bytes=size_bytes,
                    backup_id=backup_id,
                    error=error,
                    manifest_sha256=manifest_sha256,
                )
            )
            row = await session.get(BackupRunRow, UUID(run_id))
            assert row is not None  # noqa: S101
            await session.refresh(row)
        return _run(row)

    async def get(self, run_id: str) -> BackupRun | None:
        async with self._sessions.use() as session:
            row = await session.get(BackupRunRow, UUID(run_id))
        return _run(row) if row else None

    async def page(self, window: Window) -> Found[BackupRun]:
        stmt = (
            select(BackupRunRow)
            .order_by(BackupRunRow.started_at.desc(), BackupRunRow.id)
            .limit(window.limit)
            .offset(window.offset)
        )
        async with self._sessions.use() as session:
            total = (await session.execute(select(func.count()).select_from(BackupRunRow))).scalar_one()
            rows = (await session.execute(stmt)).scalars().all()
        return Found(items=[_run(row) for row in rows], total=int(total))

    async def alive_for(self, destination_id: str) -> list[BackupRun]:
        stmt = select(BackupRunRow).where(
            BackupRunRow.destination_id == UUID(destination_id),
            BackupRunRow.status == RunStatus.ok.value,
            BackupRunRow.removed_at.is_(None),
            BackupRunRow.backup_id.is_not(None),
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_run(row) for row in rows]

    async def mark_removed(self, run_id: str, at: datetime) -> None:
        async with self._sessions.use() as session:
            await session.execute(update(BackupRunRow).where(BackupRunRow.id == UUID(run_id)).values(removed_at=at))

    async def interrupt_running(self, at: datetime) -> int:
        async with self._sessions.use() as session:
            result = await session.execute(
                update(BackupRunRow)
                .where(BackupRunRow.status == RunStatus.running.value)
                .values(
                    status=RunStatus.interrupted.value,
                    stage=None,
                    finished_at=at,
                    error="interrupted: the server was restarted",
                )
            )
        return int(result.rowcount or 0)  # type: ignore[attr-defined]

    async def running(self) -> BackupRun | None:
        stmt = select(BackupRunRow).where(BackupRunRow.status == RunStatus.running.value)
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _run(row) if row else None

    async def last_finished(self) -> BackupRun | None:
        stmt = (
            select(BackupRunRow)
            .where(BackupRunRow.status != RunStatus.running.value)
            .order_by(BackupRunRow.started_at.desc())
            .limit(1)
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _run(row) if row else None

    async def stats(self) -> RunStats:
        counts = select(BackupRunRow.status, func.count()).group_by(BackupRunRow.status)
        last_ok = (
            select(BackupRunRow)
            .where(BackupRunRow.status == RunStatus.ok.value)
            .order_by(BackupRunRow.finished_at.desc())
            .limit(1)
        )
        async with self._sessions.use() as session:
            by_status = {RunStatus(name): int(total) for name, total in (await session.execute(counts)).all()}
            ok_row = (await session.execute(last_ok)).scalar_one_or_none()
        return RunStats(
            by_status=by_status,
            last_success=_run(ok_row) if ok_row else None,
            last_finished=await self.last_finished(),
        )


class SqlAdminDirectory:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def active_admin_ids(self) -> list[str]:
        stmt = (
            select(UserRow.id)
            .where(UserRow.is_instance_admin.is_(True), UserRow.status == "active")
            .order_by(UserRow.id)
        )
        async with self._sessions.use() as session:
            return list((await session.execute(stmt)).scalars().all())
