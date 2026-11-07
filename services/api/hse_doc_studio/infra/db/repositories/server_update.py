"""Запуски автообновления в Postgres."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.listing import Found, Window
from hse_doc_studio.core.server_update.entities import (
    ACTIVE_STATUSES,
    RunEvent,
    RunKind,
    RunStatus,
    RunTrigger,
    UpdateRun,
    Verify,
)
from hse_doc_studio.core.server_update.versions import known_revisions
from hse_doc_studio.infra.db.orm.server_update import UpdateRunRow
from hse_doc_studio.infra.db.session import SessionProvider

_ACTIVE = [s.value for s in ACTIVE_STATUSES]


def _event_to_json(e: RunEvent) -> dict[str, Any]:
    return {"seq": e.seq, "at": e.at.isoformat(), "phase": e.phase, "level": e.level, "message": e.message}


def _event_from_json(raw: dict[str, Any]) -> RunEvent:
    return RunEvent(
        seq=int(raw.get("seq", 0)),
        at=datetime.fromisoformat(str(raw["at"])),
        phase=str(raw.get("phase", "")),
        level=str(raw.get("level", "info")),
        message=str(raw.get("message", "")),
    )


def _run(row: UpdateRunRow) -> UpdateRun:
    return UpdateRun(
        id=str(row.id),
        kind=RunKind(row.kind),
        trigger=RunTrigger(row.trigger),
        status=RunStatus(row.status),
        phase=row.phase,
        from_version=row.from_version,
        to_version=row.to_version,
        from_revision=row.from_revision,
        to_revision=row.to_revision,
        created_at=row.created_at,
        started_at=row.started_at,
        finished_at=row.finished_at,
        requested_by=row.requested_by,
        backup_run_id=str(row.backup_run_id) if row.backup_run_id else None,
        restore_db=row.restore_db,
        db_restored=row.db_restored,
        digests_url=row.digests_url,
        verify=Verify(row.verify),
        error_code=row.error_code,
        error=row.error,
        last_seq=row.last_seq,
        events=tuple(_event_from_json(e) for e in row.events or []),
    )


def _values(run: UpdateRun) -> dict[str, Any]:
    return {
        "kind": run.kind.value,
        "trigger": run.trigger.value,
        "status": run.status.value,
        "phase": run.phase,
        "from_version": run.from_version,
        "to_version": run.to_version,
        "from_revision": run.from_revision,
        "to_revision": run.to_revision,
        "created_at": run.created_at,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "requested_by": run.requested_by,
        "backup_run_id": UUID(run.backup_run_id) if run.backup_run_id else None,
        "restore_db": run.restore_db,
        "db_restored": run.db_restored,
        "digests_url": run.digests_url,
        "verify": run.verify.value,
        "error_code": run.error_code,
        "error": run.error,
        "last_seq": run.last_seq,
        "events": [_event_to_json(e) for e in run.events],
    }


class SqlUpdateRunRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, run: UpdateRun) -> bool:
        stmt = pg_insert(UpdateRunRow).values(id=UUID(run.id), **_values(run)).on_conflict_do_nothing()
        async with self._sessions.use() as session:
            result = await session.execute(stmt)
        return bool(result.rowcount)  # type: ignore[attr-defined]

    async def get(self, run_id: str) -> UpdateRun | None:
        async with self._sessions.use() as session:
            row = await session.get(UpdateRunRow, UUID(run_id))
        return _run(row) if row else None

    async def lock(self, run_id: str) -> UpdateRun | None:
        async with self._sessions.use() as session:
            row = (
                await session.execute(select(UpdateRunRow).where(UpdateRunRow.id == UUID(run_id)).with_for_update())
            ).scalar_one_or_none()
        return _run(row) if row else None

    async def save(self, run: UpdateRun) -> None:
        async with self._sessions.use() as session:
            await session.execute(update(UpdateRunRow).where(UpdateRunRow.id == UUID(run.id)).values(**_values(run)))

    async def active(self) -> UpdateRun | None:
        stmt = select(UpdateRunRow).where(UpdateRunRow.status.in_(_ACTIVE)).limit(1)
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _run(row) if row else None

    async def claim_next(self, *, now_iso: str) -> UpdateRun | None:
        now = datetime.fromisoformat(now_iso)
        async with self._sessions.use() as session:
            row = (
                await session.execute(
                    select(UpdateRunRow)
                    .where(UpdateRunRow.status == RunStatus.queued.value)
                    .order_by(UpdateRunRow.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            row.status = RunStatus.running.value
            row.started_at = now
            row.phase = "preflight"
            await session.flush()
            return _run(row)

    async def page(self, window: Window) -> Found[UpdateRun]:
        stmt = (
            select(UpdateRunRow)
            .order_by(UpdateRunRow.created_at.desc(), UpdateRunRow.id)
            .limit(window.limit)
            .offset(window.offset)
        )
        async with self._sessions.use() as session:
            total = (await session.execute(select(func.count()).select_from(UpdateRunRow))).scalar_one()
            rows = (await session.execute(stmt)).scalars().all()
        return Found(items=[_run(r) for r in rows], total=int(total))

    async def _one(self, *conditions: Any) -> UpdateRun | None:
        stmt = select(UpdateRunRow).where(*conditions).order_by(UpdateRunRow.created_at.desc()).limit(1)
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return _run(row) if row else None

    async def last_finished(self) -> UpdateRun | None:
        return await self._one(UpdateRunRow.status.not_in(_ACTIVE))

    async def last_succeeded_update(self) -> UpdateRun | None:
        return await self._one(
            UpdateRunRow.status == RunStatus.succeeded.value, UpdateRunRow.kind == RunKind.update.value
        )

    async def failed_targets(self) -> frozenset[str]:
        failed = select(UpdateRunRow.to_version).where(
            UpdateRunRow.kind == RunKind.update.value,
            UpdateRunRow.status.in_([RunStatus.rolled_back.value, RunStatus.failed.value]),
        )
        # Версия, с которой админ откатился вручную, автоматически не возвращается.
        undone = select(UpdateRunRow.from_version).where(
            UpdateRunRow.kind.in_([RunKind.rollback.value, RunKind.downgrade.value]),
            UpdateRunRow.status == RunStatus.succeeded.value,
        )
        async with self._sessions.use() as session:
            found = (await session.execute(failed)).scalars().all()
            found = [*found, *(await session.execute(undone)).scalars().all()]
        return frozenset(found)

    async def known_revisions(self) -> dict[str, str]:
        stmt = (
            select(UpdateRunRow)
            .where(
                UpdateRunRow.kind.in_([RunKind.update.value, RunKind.downgrade.value]),
                UpdateRunRow.status.in_([RunStatus.succeeded.value, RunStatus.rolled_back.value]),
            )
            .order_by(UpdateRunRow.created_at)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return known_revisions(_run(r) for r in rows)

    async def counts(self) -> dict[RunStatus, int]:
        stmt = select(UpdateRunRow.status, func.count()).group_by(UpdateRunRow.status)
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        return {RunStatus(status): int(n) for status, n in rows}

    async def recent(self, limit: int) -> list[UpdateRun]:
        stmt = select(UpdateRunRow).order_by(UpdateRunRow.created_at.desc()).limit(limit)
        async with self._sessions.use() as session:
            return [_run(r) for r in (await session.execute(stmt)).scalars().all()]
