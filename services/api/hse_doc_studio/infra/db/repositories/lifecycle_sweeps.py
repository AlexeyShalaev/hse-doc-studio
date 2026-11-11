"""Postgres: прогоны «Освободить место». Один идущий (частичный уникальный индекс), 20 последних."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.lifecycle.sweeps import (
    ACTIVE_STATUSES,
    LifecycleSweep,
    StepStatus,
    SweepStatus,
    SweepStep,
    closed_steps,
)
from hse_doc_studio.infra.db.orm.lifecycle import LifecycleSweepRow
from hse_doc_studio.infra.db.session import SessionProvider


def _uuid(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _step_json(step: SweepStep) -> dict[str, Any]:
    return {
        "key": step.key,
        "status": step.status.value,
        "removed": step.removed,
        "partitions_dropped": step.partitions_dropped,
        "more": step.more,
        "bytes_before": step.bytes_before,
        "bytes_after": step.bytes_after,
        "error": step.error,
    }


def _step(raw: dict[str, Any]) -> SweepStep:
    return SweepStep(
        key=str(raw["key"]),
        status=StepStatus(raw.get("status", StepStatus.pending.value)),
        removed=int(raw.get("removed") or 0),
        partitions_dropped=int(raw.get("partitions_dropped") or 0),
        more=bool(raw.get("more", False)),
        bytes_before=raw.get("bytes_before"),
        bytes_after=raw.get("bytes_after"),
        error=raw.get("error"),
    )


def _sweep(row: LifecycleSweepRow) -> LifecycleSweep:
    return LifecycleSweep(
        id=str(row.id),
        status=SweepStatus(row.status),
        started_by=row.started_by,
        started_at=row.started_at,
        updated_at=row.updated_at,
        finished_at=row.finished_at,
        steps=tuple(_step(s) for s in row.steps or []),
    )


class SqlLifecycleSweeps:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def create(self, sweep: LifecycleSweep, *, keep: int) -> bool:
        stmt = (
            pg_insert(LifecycleSweepRow)
            .values(
                id=UUID(sweep.id),
                status=sweep.status.value,
                started_by=sweep.started_by,
                started_at=sweep.started_at,
                updated_at=sweep.updated_at,
                finished_at=sweep.finished_at,
                steps=[_step_json(s) for s in sweep.steps],
            )
            .on_conflict_do_nothing()
        )
        recent = select(LifecycleSweepRow.id).order_by(LifecycleSweepRow.started_at.desc()).limit(keep)
        async with self._sessions.use() as db:
            created = bool((await db.execute(stmt)).rowcount)  # type: ignore[attr-defined]
            if created:
                await db.execute(
                    delete(LifecycleSweepRow).where(
                        LifecycleSweepRow.status.not_in(ACTIVE_STATUSES), LifecycleSweepRow.id.not_in(recent)
                    )
                )
        return created

    async def get(self, sweep_id: str) -> LifecycleSweep | None:
        key = _uuid(sweep_id)
        if key is None:
            return None
        async with self._sessions.use() as db:
            row = await db.get(LifecycleSweepRow, key)
        return _sweep(row) if row else None

    async def latest(self) -> LifecycleSweep | None:
        # Идущий прогон важнее последнего по времени: запуск и итог разделены, но идущий всегда самый свежий.
        stmt = (
            select(LifecycleSweepRow)
            .order_by(LifecycleSweepRow.status.in_(ACTIVE_STATUSES).desc(), LifecycleSweepRow.started_at.desc())
            .limit(1)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
        return _sweep(row) if row else None

    async def save_steps(self, sweep_id: str, steps: Sequence[SweepStep], *, at: datetime) -> SweepStatus | None:
        stmt = (
            update(LifecycleSweepRow)
            .where(LifecycleSweepRow.id == UUID(sweep_id), LifecycleSweepRow.status.in_(ACTIVE_STATUSES))
            .values(steps=[_step_json(s) for s in steps], updated_at=at)
            .returning(LifecycleSweepRow.status)
        )
        async with self._sessions.use() as db:
            status = (await db.execute(stmt)).scalar_one_or_none()
            if status is None:
                status = (
                    await db.execute(select(LifecycleSweepRow.status).where(LifecycleSweepRow.id == UUID(sweep_id)))
                ).scalar_one_or_none()
        return SweepStatus(status) if status is not None else None

    async def request_cancel(self, sweep_id: str, *, at: datetime) -> LifecycleSweep | None:
        key = _uuid(sweep_id)
        if key is None:
            return None
        async with self._sessions.use() as db:
            await db.execute(
                update(LifecycleSweepRow)
                .where(LifecycleSweepRow.id == key, LifecycleSweepRow.status == SweepStatus.running.value)
                .values(status=SweepStatus.cancelling.value)
            )
            row = (await db.execute(select(LifecycleSweepRow).where(LifecycleSweepRow.id == key))).scalar_one_or_none()
        return _sweep(row) if row else None

    async def finish(
        self, sweep_id: str, status: SweepStatus, steps: Sequence[SweepStep], *, at: datetime
    ) -> LifecycleSweep | None:
        stmt = (
            update(LifecycleSweepRow)
            .where(LifecycleSweepRow.id == UUID(sweep_id), LifecycleSweepRow.status.in_(ACTIVE_STATUSES))
            .values(status=status.value, steps=[_step_json(s) for s in steps], updated_at=at, finished_at=at)
            .returning(LifecycleSweepRow)
        )
        async with self._sessions.use() as db:
            row = (await db.execute(stmt)).scalar_one_or_none()
        return _sweep(row) if row else None

    async def interrupt_stale(self, *, before: datetime, at: datetime) -> list[LifecycleSweep]:
        stmt = (
            update(LifecycleSweepRow)
            .where(LifecycleSweepRow.status.in_(ACTIVE_STATUSES), LifecycleSweepRow.updated_at < before)
            .values(status=SweepStatus.interrupted.value, updated_at=at, finished_at=at)
            .returning(LifecycleSweepRow)
        )
        out: list[LifecycleSweep] = []
        async with self._sessions.use() as db:
            for row in (await db.execute(stmt)).scalars().all():
                steps = closed_steps([_step(s) for s in row.steps or []])
                await db.execute(
                    update(LifecycleSweepRow)
                    .where(LifecycleSweepRow.id == row.id)
                    .values(steps=[_step_json(s) for s in steps])
                )
                out.append(replace(_sweep(row), steps=steps))
        return out
