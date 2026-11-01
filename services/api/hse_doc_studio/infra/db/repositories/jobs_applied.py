"""Метка применённого итога задачи в таблице очереди."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.queue import QueuedJob
from hse_doc_studio.infra.db.orm.jobs import JobRow
from hse_doc_studio.infra.db.repositories.jobs import job_from_row
from hse_doc_studio.infra.db.session import SessionProvider

_TERMINAL = tuple(state.value for state in JobState if state.is_terminal)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqlJobApplyLedger:
    def __init__(self, sessions: SessionProvider, clock: Callable[[], datetime] = _utcnow) -> None:
        self._sessions = sessions
        self._clock = clock

    async def mark_applied(self, job_id: UUID) -> bool:
        """Метка ставится одним условным UPDATE: победил тот, кто увидел пустое `applied_at`."""
        async with self._sessions.use() as session:
            result = await session.execute(
                update(JobRow)
                .where(JobRow.id == job_id, JobRow.applied_at.is_(None), JobRow.state.in_(_TERMINAL))
                .values(applied_at=self._clock())
                .returning(JobRow.id)
            )
            return result.first() is not None

    async def list_unapplied(self) -> tuple[QueuedJob, ...]:
        stmt = (
            select(JobRow)
            .where(JobRow.applied_at.is_(None), JobRow.state.in_(_TERMINAL))
            .order_by(JobRow.seq)
            .execution_options(populate_existing=True)
        )
        async with self._sessions.use() as session:
            return tuple(job_from_row(row) for row in (await session.execute(stmt)).scalars())
