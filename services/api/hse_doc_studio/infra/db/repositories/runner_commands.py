"""Postgres: команды раннеру (`runner_commands`) и последний замер диска (`runners.disk`)."""

from __future__ import annotations

import builtins
from collections.abc import Collection
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, ColumnElement, case, cast, delete, func, or_, select, true, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.jobs.codec import decode, encode
from hse_doc_studio.core.jobs.control import COMMANDS_KEPT_PER_RUNNER, StoredDiskBrief, StoredDiskReport
from hse_doc_studio.core.jobs.disk import (
    COMMAND_OPEN_STATES,
    CommandProgress,
    DiskCleanupPayload,
    DiskMeasurePayload,
    RunnerCommand,
    RunnerCommandKind,
    RunnerCommandPayload,
    RunnerCommandState,
    RunnerDiskReport,
)
from hse_doc_studio.infra.db.orm.jobs import RunnerCommandRow, RunnerRow
from hse_doc_studio.infra.db.session import SessionProvider

_OPEN = sorted(state.value for state in COMMAND_OPEN_STATES)
_FINISHED = sorted(state.value for state in RunnerCommandState if state.finished)
_IN_FLIGHT = sorted(
    s.value for s in (RunnerCommandState.delivered, RunnerCommandState.running, RunnerCommandState.cancelling)
)


def _payload(kind: RunnerCommandKind, raw: dict[str, Any]) -> RunnerCommandPayload:
    if kind is RunnerCommandKind.disk_cleanup:
        return decode(DiskCleanupPayload, raw)
    return DiskMeasurePayload()


def _progress(raw: dict[str, Any] | None) -> CommandProgress | None:
    # Ход пишет только `/control/{id}/progress` после проверки схемой; другая форма читается как «хода нет».
    if not raw:
        return None
    try:
        return decode(CommandProgress, raw)
    except (TypeError, ValueError, KeyError):
        return None


def _command(row: RunnerCommandRow) -> RunnerCommand:
    kind = RunnerCommandKind(row.kind)
    return RunnerCommand(
        id=row.id,
        runner_id=row.runner_id,
        kind=kind,
        payload=_payload(kind, row.payload),
        state=RunnerCommandState(row.state),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
        progress=_progress(row.progress),
        delivered_at=row.delivered_at,
        finished_at=row.finished_at,
    )


def _payload_json(payload: RunnerCommandPayload) -> dict[str, Any]:
    raw = encode(payload)
    assert isinstance(raw, dict)  # noqa: S101 — датакласс кодируется словарём
    return raw


def _progress_json(progress: CommandProgress) -> dict[str, Any]:
    raw = encode(progress)
    assert isinstance(raw, dict)  # noqa: S101 — датакласс кодируется словарём
    return raw


def _for_runner(runner_id: str | None) -> ColumnElement[bool]:
    return RunnerCommandRow.runner_id == runner_id if runner_id is not None else true()


class SqlRunnerCommandRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, command: RunnerCommand, *, keep: int = COMMANDS_KEPT_PER_RUNNER) -> bool:
        stmt = (
            pg_insert(RunnerCommandRow)
            .values(
                id=command.id,
                runner_id=command.runner_id,
                kind=command.kind.value,
                payload=_payload_json(command.payload),
                state=command.state.value,
                progress=_progress_json(command.progress) if command.progress is not None else None,
                created_by=command.created_by,
                created_at=command.created_at,
                updated_at=command.updated_at,
                delivered_at=command.delivered_at,
                finished_at=command.finished_at,
            )
            # Единственный уникальный индекс кроме ключа: незавершённая очистка раннера.
            .on_conflict_do_nothing()
        )
        recent = (
            select(RunnerCommandRow.id)
            .where(RunnerCommandRow.runner_id == command.runner_id)
            .order_by(RunnerCommandRow.created_at.desc(), RunnerCommandRow.id.desc())
            .limit(keep)
        )
        async with self._sessions.use() as db:
            if not (await db.execute(stmt)).rowcount:  # type: ignore[attr-defined]
                return False
            await db.execute(
                delete(RunnerCommandRow).where(
                    RunnerCommandRow.runner_id == command.runner_id,
                    RunnerCommandRow.state.in_(_FINISHED),
                    RunnerCommandRow.id.not_in(recent),
                )
            )
        return True

    async def get(self, command_id: UUID) -> RunnerCommand | None:
        async with self._sessions.use() as db:
            row = await db.get(RunnerCommandRow, command_id, populate_existing=True)
            return _command(row) if row else None

    async def list_for_runner(self, runner_id: str, *, limit: int) -> builtins.list[RunnerCommand]:
        stmt = (
            select(RunnerCommandRow)
            .where(RunnerCommandRow.runner_id == runner_id)
            .order_by(RunnerCommandRow.created_at.desc(), RunnerCommandRow.id.desc())
            .limit(limit)
        )
        async with self._sessions.use() as db:
            return [_command(row) for row in (await db.execute(stmt)).scalars()]

    async def find_open(self, runner_id: str, kind: RunnerCommandKind) -> RunnerCommand | None:
        stmt = (
            select(RunnerCommandRow)
            .where(
                RunnerCommandRow.runner_id == runner_id,
                RunnerCommandRow.kind == kind.value,
                RunnerCommandRow.state.in_(_OPEN),
            )
            .order_by(RunnerCommandRow.created_at.desc())
            .limit(1)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _command(row) if row else None

    async def claim(
        self, runner_id: str, kinds: Collection[RunnerCommandKind], *, now: datetime, not_before: datetime
    ) -> RunnerCommand | None:
        if not kinds:
            return None
        oldest = (
            select(RunnerCommandRow.id)
            .where(
                RunnerCommandRow.runner_id == runner_id,
                RunnerCommandRow.state == RunnerCommandState.queued.value,
                RunnerCommandRow.kind.in_([kind.value for kind in kinds]),
                RunnerCommandRow.created_at >= not_before,
            )
            .order_by(RunnerCommandRow.created_at, RunnerCommandRow.id)
            .limit(1)
            .with_for_update(skip_locked=True)
            .scalar_subquery()
        )
        stmt = (
            update(RunnerCommandRow)
            .where(RunnerCommandRow.id == oldest, RunnerCommandRow.state == RunnerCommandState.queued.value)
            .values(state=RunnerCommandState.delivered.value, delivered_at=now, updated_at=now)
            .returning(RunnerCommandRow)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _command(row) if row else None

    async def transition(
        self,
        command_id: UUID,
        *,
        expected: RunnerCommandState,
        to: RunnerCommandState,
        now: datetime,
        progress: CommandProgress | None = None,
    ) -> RunnerCommand | None:
        values: dict[str, object] = {"state": to.value, "updated_at": now}
        if progress is not None:
            values["progress"] = _progress_json(progress)
        if to is RunnerCommandState.delivered:
            values["delivered_at"] = now
        if to.finished:
            values["finished_at"] = now
        stmt = (
            update(RunnerCommandRow)
            .where(RunnerCommandRow.id == command_id, RunnerCommandRow.state == expected.value)
            .values(**values)
            .returning(RunnerCommandRow)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
            return _command(row) if row else None

    async def expire_queued(
        self, *, before: datetime, now: datetime, runner_id: str | None = None
    ) -> builtins.list[RunnerCommand]:
        stmt = (
            update(RunnerCommandRow)
            .where(
                _for_runner(runner_id),
                RunnerCommandRow.state == RunnerCommandState.queued.value,
                RunnerCommandRow.created_at < before,
            )
            .values(state=RunnerCommandState.expired.value, updated_at=now, finished_at=now)
            .returning(RunnerCommandRow)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions.use() as db:
            return [_command(row) for row in (await db.execute(stmt)).scalars()]

    async def lose(
        self, *, silent_before: datetime, now: datetime, runner_id: str | None = None
    ) -> builtins.list[RunnerCommand]:
        gone = (
            select(RunnerRow.id)
            .where(
                RunnerRow.id == RunnerCommandRow.runner_id,
                or_(
                    RunnerRow.revoked_at.is_not(None),
                    RunnerRow.offline_at >= RunnerCommandRow.updated_at,
                ),
            )
            .exists()
        )
        stmt = (
            update(RunnerCommandRow)
            .where(
                _for_runner(runner_id),
                RunnerCommandRow.state.in_(_IN_FLIGHT),
                or_(RunnerCommandRow.updated_at < silent_before, gone),
            )
            .values(state=RunnerCommandState.lost.value, updated_at=now, finished_at=now)
            .returning(RunnerCommandRow)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions.use() as db:
            return [_command(row) for row in (await db.execute(stmt)).scalars()]


def _disk(raw: dict[str, Any] | None, received_at: datetime | None) -> StoredDiskReport | None:
    # Замер пишет только `/disk` после проверки схемой; запись другой версии формы читается как «замера нет».
    if not raw or received_at is None:
        return None
    try:
        return StoredDiskReport(report=decode(RunnerDiskReport, raw), received_at=received_at)
    except (TypeError, ValueError, KeyError):
        return None


class SqlRunnerDiskStore:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def set_disk(self, runner_id: str, report: RunnerDiskReport, now: datetime) -> bool:
        stmt = (
            update(RunnerRow)
            .where(RunnerRow.id == runner_id, RunnerRow.revoked_at.is_(None))
            .values(disk=encode(report), disk_at=now)
            .execution_options(synchronize_session=False)
        )
        async with self._sessions.use() as db:
            return (await db.execute(stmt)).rowcount > 0  # type: ignore[attr-defined]

    async def get_disk(self, runner_id: str) -> StoredDiskReport | None:
        stmt = select(RunnerRow.disk, RunnerRow.disk_at).where(RunnerRow.id == runner_id)
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).first()
        return _disk(row.disk, row.disk_at) if row is not None else None

    async def list_disks(self) -> dict[str, StoredDiskReport]:
        stmt = select(RunnerRow.id, RunnerRow.disk, RunnerRow.disk_at).where(RunnerRow.disk.is_not(None))
        found: dict[str, StoredDiskReport] = {}
        async with self._sessions.use() as db:
            for row in (await db.execute(stmt)).all():
                stored = _disk(row.disk, row.disk_at)
                if stored is not None:
                    found[row.id] = stored
        return found

    async def list_disk_briefs(self, runner_ids: Collection[str] | None = None) -> dict[str, StoredDiskBrief]:
        # Тот же расчёт, что `disk_cleanable_bytes`, но в базе: отчёт целиком (до 64 КБ) не читается и не разбирается.
        disk = RunnerRow.disk
        docker = case(
            (
                disk[("docker", "available")].astext == "true",
                cast(disk[("docker", "cleanable_bytes")].astext, BigInteger),
            ),
            else_=0,
        )
        cache = func.coalesce(cast(disk[("cache", "blobs", "bytes")].astext, BigInteger), 0) + func.coalesce(
            cast(disk[("cache", "workspaces", "bytes")].astext, BigInteger), 0
        )
        stmt = select(
            RunnerRow.id,
            disk["measured_at"].astext.label("measured_at"),
            RunnerRow.disk_at,
            (func.coalesce(docker, 0) + cache).label("cleanable"),
        ).where(RunnerRow.disk.is_not(None), RunnerRow.disk_at.is_not(None))
        if runner_ids is not None:
            if not runner_ids:
                return {}
            stmt = stmt.where(RunnerRow.id.in_(list(runner_ids)))
        found: dict[str, StoredDiskBrief] = {}
        async with self._sessions.use() as db:
            for row in (await db.execute(stmt)).all():
                measured = _moment(row.measured_at)
                if measured is None or row.disk_at is None:
                    continue
                found[row.id] = StoredDiskBrief(
                    cleanable_bytes=max(int(row.cleanable or 0), 0), measured_at=measured, received_at=row.disk_at
                )
        return found


def _moment(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
