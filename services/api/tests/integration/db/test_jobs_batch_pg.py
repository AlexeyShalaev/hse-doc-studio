"""Пакет «Собрать все» на Postgres: колонка и индекс миграции, сводка пакета по всем страницам, фильтр."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.admin import JobAdminFilter
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.repositories.jobs_admin import SqlJobAdminReader
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

_BEFORE = "rd_01_runner_deployment"
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


async def _jobs_schema(engine: AsyncEngine) -> tuple[set[str], set[str]]:
    async with engine.connect() as conn:
        columns = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("jobs")})
        indexes = await conn.run_sync(lambda c: {ix["name"] for ix in inspect(c).get_indexes("jobs")})
    return columns, indexes


async def test__migration__batch_id_column_and_index__added_and_dropped(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine)
    columns, indexes = await _jobs_schema(pg_engine)
    assert "batch_id" in columns
    assert "ix_jobs_batch_id" in indexes

    await migrator.downgrade(pg_engine, _BEFORE)
    columns, indexes = await _jobs_schema(pg_engine)
    assert "batch_id" not in columns
    assert "ix_jobs_batch_id" not in indexes

    await migrator.upgrade(pg_engine)
    assert await migrator.check_drift(pg_engine) == []


def _request(project: UUID, user: UUID, batch: UUID | None) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=uuid4(),
        kind=JobKind.compile,
        project_id=project,
        user_id=user,
        tags=frozenset({"tex"}),
        payload={},
        batch_id=batch,
    )


async def test__admin_reader__batch_summary_counts_the_whole_batch_and_filter_finds_it(
    pg_migrated_engine: AsyncEngine,
) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    ticks = iter(NOW + timedelta(seconds=i) for i in range(100))
    queue = PostgresJobQueue(sessions, clock=lambda: next(ticks))
    reader = SqlJobAdminReader(sessions)
    project, user, batch = uuid4(), uuid4(), uuid4()
    jobs = [(await queue.enqueue(_request(project, user, batch))).job for _ in range(3)]
    single = (await queue.enqueue(_request(project, user, None))).job
    await queue.request_cancel(jobs[1].id)

    page = await reader.list_jobs(JobAdminFilter(), before_seq=None, limit=2)
    only = await reader.list_jobs(JobAdminFilter(batch_id=batch), before_seq=None, limit=50)
    one = await reader.get(jobs[0].id)

    assert [item.job.id for item in page.items] == [single.id, jobs[2].id]
    assert page.items[0].batch is None
    summary = page.items[1].batch
    assert summary is not None
    assert (summary.id, summary.total) == (batch, 3)
    assert summary.by_state == {JobState.queued: 2, JobState.cancelled: 1}
    assert summary.queued_at == jobs[0].queued_at
    assert summary.active == 2
    assert sorted(item.job.id for item in only.items) == sorted(job.id for job in jobs)
    assert one is not None
    assert one.batch == summary
