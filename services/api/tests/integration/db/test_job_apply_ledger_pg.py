"""SqlJobApplyLedger: метка применённого ставится один раз, список ждущих довершения."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.queue import EnqueueRequest, RunnerRef
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.repositories.jobs_applied import SqlJobApplyLedger
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg


def _request(job_id: UUID) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=job_id,
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=uuid4(),
        tags=frozenset({"tex"}),
        payload={},
    )


async def _finished_job(queue: PostgresJobQueue, status: JobStatus = JobStatus.succeeded) -> UUID:
    job_id = uuid4()
    await queue.enqueue(_request(job_id))
    job = await queue.claim(RunnerRef(id=uuid4(), tags=frozenset({"tex"})), lease_s=45)
    assert job is not None
    await queue.complete(job.id, job.attempt, status)
    return job.id


async def test__mark_applied__concurrent_marks__exactly_one_wins(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    queue, ledger = PostgresJobQueue(sessions), SqlJobApplyLedger(sessions)
    job_id = await _finished_job(queue)

    outcomes = await asyncio.gather(*(ledger.mark_applied(job_id) for _ in range(8)))

    assert sorted(outcomes) == [False] * 7 + [True]


async def test__list_unapplied__terminal_without_mark_only(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    queue, ledger = PostgresJobQueue(sessions), SqlJobApplyLedger(sessions)
    done = await _finished_job(queue)
    failed = await _finished_job(queue, JobStatus.failed)
    marked = await _finished_job(queue)
    running = uuid4()
    await queue.enqueue(_request(running))
    await ledger.mark_applied(marked)

    assert [job.id for job in await ledger.list_unapplied()] == [done, failed]


async def test__mark_applied__job_not_terminal__refused(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    queue, ledger = PostgresJobQueue(sessions), SqlJobApplyLedger(sessions)
    job_id = uuid4()
    await queue.enqueue(_request(job_id))

    assert await ledger.mark_applied(job_id) is False
