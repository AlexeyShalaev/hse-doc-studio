"""Чтение очереди для админки: страницы с фильтрами и сводка. Записей не делает."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select

from hse_doc_studio.core.jobs.admin import JobAdminFilter, JobAdminPage, QueueStats
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.jobs.routing import JobRoute
from hse_doc_studio.infra.db.orm.jobs import JobRow
from hse_doc_studio.infra.db.repositories.jobs import job_from_row
from hse_doc_studio.infra.db.session import SessionProvider

_WAIT_WINDOW = timedelta(hours=1)


class SqlJobAdminReader:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def list_jobs(self, flt: JobAdminFilter, *, before_seq: int | None, limit: int) -> JobAdminPage:
        stmt = select(JobRow).order_by(JobRow.seq.desc()).limit(limit + 1).execution_options(populate_existing=True)
        if flt.state is not None:
            stmt = stmt.where(JobRow.state == flt.state.value)
        if flt.kind is not None:
            stmt = stmt.where(JobRow.kind == flt.kind.value)
        if flt.user_id is not None:
            stmt = stmt.where(JobRow.user_id == flt.user_id)
        if flt.project_id is not None:
            stmt = stmt.where(JobRow.project_id == flt.project_id)
        if flt.runner_scope is not None:
            stmt = stmt.where(JobRow.runner_scope == flt.runner_scope.value)
        if before_seq is not None:
            stmt = stmt.where(JobRow.seq < before_seq)
        async with self._sessions.use() as session:
            rows = list((await session.execute(stmt)).scalars())
        page = rows[:limit]
        more = len(rows) > limit
        return JobAdminPage(
            items=tuple(job_from_row(r) for r in page),
            next_before_seq=page[-1].seq if more and page else None,
        )

    async def stats(self, now: datetime) -> QueueStats:
        wait = func.extract("epoch", JobRow.started_at - JobRow.queued_at)
        # «Ждут раннера» без ретрансляций ИИ и без сборок, которые пока ждут личный раннер владельца в окне.
        waiting_runner = and_(
            JobRow.state == JobState.queued.value,
            JobRow.route != JobRoute.pinned.value,
            or_(JobRow.route != JobRoute.personal_first.value, JobRow.personal_until <= now),
        )
        async with self._sessions.use() as session:
            by_state = {
                JobState(state): count
                for state, count in (
                    await session.execute(select(JobRow.state, func.count()).group_by(JobRow.state))
                ).all()
            }
            by_class = {
                int(cls): count
                for cls, count in (
                    await session.execute(
                        select(JobRow.priority_class, func.count())
                        .where(waiting_runner)
                        .group_by(JobRow.priority_class)
                    )
                ).all()
            }
            oldest = (await session.execute(select(func.min(JobRow.queued_at)).where(waiting_runner))).scalar_one()
            p50, p95 = (
                await session.execute(
                    select(
                        func.percentile_cont(0.5).within_group(wait),
                        func.percentile_cont(0.95).within_group(wait),
                    ).where(JobRow.started_at.is_not(None), JobRow.started_at >= now - _WAIT_WINDOW)
                )
            ).one()
        return QueueStats(
            by_state=by_state,
            queued_by_class=by_class,
            oldest_queued_at=oldest,
            wait_p50_s=float(p50) if p50 is not None else None,
            wait_p95_s=float(p95) if p95 is not None else None,
        )
