"""Чтение очереди для админки: страницы с фильтрами и подписями, сводка, пикер проектов. Записей не делает."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, String, and_, cast, func, select, text, true
from sqlalchemy.engine import Row

from hse_doc_studio.core.jobs.admin import JobAdminFilter, JobAdminPage, JobListing, QueueStats
from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.listing import PickerItem, PickerResult
from hse_doc_studio.infra.db.orm.identity import UserRow
from hse_doc_studio.infra.db.orm.jobs import JobRow, RunnerRow
from hse_doc_studio.infra.db.orm.orgs import OrgRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.jobs import job_from_row
from hse_doc_studio.infra.db.search import matches_any
from hse_doc_studio.infra.db.session import SessionProvider

_WAIT_WINDOW = timedelta(hours=1)


def _hex(column: Any) -> ColumnElement[str]:
    """UUID очереди в виде id строки (32 hex без дефисов): так хранятся id людей и раннеров."""
    return func.replace(cast(column, String), "-", "")


def _with_names() -> Select[*tuple[Any, ...]]:
    """Задачи с подписями. Организация берётся у проекта: в `jobs.org_id` лежит ключ квот, а не id организации."""
    return (
        select(JobRow, UserRow.name, UserRow.email, OrgRow.name, ProjectRow.name, RunnerRow.name)
        .outerjoin(UserRow, UserRow.id == _hex(JobRow.user_id))
        .outerjoin(ProjectRow, ProjectRow.id == JobRow.project_id)
        .outerjoin(OrgRow, and_(JobRow.org_id.is_not(None), OrgRow.id == ProjectRow.owner_org_id))
        .outerjoin(RunnerRow, RunnerRow.id == _hex(JobRow.runner_id))
        .execution_options(populate_existing=True)
    )


def _listing(row: Row[*tuple[Any, ...]]) -> JobListing:
    return JobListing(
        job=job_from_row(row[0]),
        user_name=row[1],
        user_email=row[2],
        org_name=row[3],
        project_name=row[4],
        runner_name=row[5],
    )


def _conditions(flt: JobAdminFilter) -> list[ColumnElement[bool]]:
    found: list[ColumnElement[bool]] = []
    if flt.states:
        found.append(JobRow.state.in_(sorted(s.value for s in flt.states)))
    if flt.kinds:
        found.append(JobRow.kind.in_(sorted(k.value for k in flt.kinds)))
    for column, value in (
        (JobRow.user_id, flt.user_id),
        (JobRow.org_id, flt.org_id),
        (JobRow.project_id, flt.project_id),
        (JobRow.runner_id, flt.runner_id),
    ):
        if value is not None:
            found.append(column == value)
    if flt.queued_from is not None:
        found.append(JobRow.queued_at >= flt.queued_from)
    if flt.queued_to is not None:
        found.append(JobRow.queued_at < flt.queued_to)
    return found


class SqlJobAdminReader:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def list_jobs(self, flt: JobAdminFilter, *, before_seq: int | None, limit: int) -> JobAdminPage:
        stmt = _with_names().where(*_conditions(flt)).order_by(JobRow.seq.desc()).limit(limit + 1)
        if before_seq is not None:
            stmt = stmt.where(JobRow.seq < before_seq)
        async with self._sessions.use() as session:
            rows = list((await session.execute(stmt)).all())
            estimate = await self._estimate(session) if flt.empty else None
        page = rows[:limit]
        more = len(rows) > limit
        return JobAdminPage(
            items=tuple(_listing(r) for r in page),
            next_before_seq=page[-1][0].seq if more and page else None,
            total_estimate=estimate,
        )

    @staticmethod
    async def _estimate(session: Any) -> int | None:
        """Число строк по статистике планировщика: без COUNT(*) по сотням тысяч задач. До ANALYZE оценки нет."""
        found = (
            await session.execute(text("SELECT reltuples::bigint FROM pg_class WHERE oid = 'jobs'::regclass"))
        ).scalar_one_or_none()
        return int(found) if found is not None and found >= 0 else None

    async def get(self, job_id: UUID) -> JobListing | None:
        async with self._sessions.use() as session:
            row = (await session.execute(_with_names().where(JobRow.id == job_id))).first()
        return None if row is None else _listing(row)

    async def stats(self, now: datetime) -> QueueStats:
        wait = func.extract("epoch", JobRow.started_at - JobRow.queued_at)
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
                        .where(JobRow.state == JobState.queued.value)
                        .group_by(JobRow.priority_class)
                    )
                ).all()
            }
            oldest = (
                await session.execute(select(func.min(JobRow.queued_at)).where(JobRow.state == JobState.queued.value))
            ).scalar_one()
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


class SqlAdminProjectPicker:
    """Проекты установки для фильтра очереди; подпись это владелец (человек или организация)."""

    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def pick(self, q: str | None, limit: int) -> PickerResult:
        stmt = (
            select(ProjectRow.id, ProjectRow.name, func.coalesce(OrgRow.name, UserRow.name))
            .outerjoin(UserRow, UserRow.id == ProjectRow.owner_user_id)
            .outerjoin(OrgRow, OrgRow.id == ProjectRow.owner_org_id)
            .where(ProjectRow.deleted_at.is_(None), matches_any(q, [ProjectRow.name]) if q else true())
            .order_by(func.lower(ProjectRow.name), ProjectRow.id)
            .limit(limit + 1)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        items = tuple(PickerItem(kind="project", id=str(row[0]), name=row[1], detail=row[2]) for row in rows[:limit])
        return PickerResult(items=items, has_more=len(rows) > limit)
