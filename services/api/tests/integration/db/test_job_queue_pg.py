"""Postgres-очередь задач: параллельные раннеры, лимиты под гонкой, состояние справедливости и план запроса."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import EnqueueRequest, QueuedJob, RunnerRef
from hse_doc_studio.core.jobs.scheduler import QueueQuota
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

LEASE_S = 45.0


def _queue(engine: AsyncEngine) -> PostgresJobQueue:
    return PostgresJobQueue(SessionProvider(create_sessionmaker(engine)))


def _request(user: UUID, **kwargs: object) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=uuid4(),
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=user,
        tags=frozenset({"tex"}),
        payload={"n": 1},
        **kwargs,  # type: ignore[arg-type]
    )


def _runner() -> RunnerRef:
    return RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1)


async def _drain(queue: PostgresJobQueue, runners: int, quota: QueueQuota | None = None) -> list[QueuedJob]:
    results = await asyncio.gather(
        *(queue.claim(_runner(), lease_s=LEASE_S, quota=quota) for _ in range(runners)),
    )
    return [job for job in results if job is not None]


async def test__claim__twenty_concurrent_claimers__no_job_taken_twice(pg_migrated_engine: AsyncEngine) -> None:
    queue = _queue(pg_migrated_engine)
    for _ in range(12):
        await queue.enqueue(_request(uuid4()))

    taken = await _drain(queue, 20)

    assert len(taken) == 12
    assert len({job.id for job in taken}) == 12
    assert all(job.state is JobState.running and job.attempt == 1 for job in taken)
    assert await queue.list(state=JobState.queued) == ()


async def test__claim__twenty_claimers_fewer_jobs__rest_get_none(pg_migrated_engine: AsyncEngine) -> None:
    queue = _queue(pg_migrated_engine)
    for _ in range(3):
        await queue.enqueue(_request(uuid4()))

    taken = await _drain(queue, 20)

    assert len(taken) == 3
    assert len({job.id for job in taken}) == 3


async def test__claim__user_cap_under_race__is_not_exceeded(pg_migrated_engine: AsyncEngine) -> None:
    queue = _queue(pg_migrated_engine)
    user = uuid4()
    for _ in range(6):
        await queue.enqueue(_request(user))

    taken = await _drain(queue, 10, QueueQuota(max_running_per_user=2))

    assert len(taken) == 2


async def test__enqueue__concurrent_same_user__gets_distinct_increasing_vtimes(
    pg_migrated_engine: AsyncEngine,
) -> None:
    queue = _queue(pg_migrated_engine)
    user = uuid4()

    outcomes = await asyncio.gather(*(queue.enqueue(_request(user)) for _ in range(10)))

    assert sorted(o.job.vtime for o in outcomes) == [float(n) for n in range(1, 11)]


async def test__queue_state__survives_new_queue_instance(pg_migrated_engine: AsyncEngine) -> None:
    first = _queue(pg_migrated_engine)
    user = uuid4()
    for _ in range(3):
        await first.enqueue(_request(user))
    for _ in range(3):
        assert await first.claim(_runner(), lease_s=LEASE_S) is not None

    # Новый экземпляр (перезапуск api) продолжает счёт, а не начинает с нуля.
    late = await _queue(pg_migrated_engine).enqueue(_request(uuid4()))

    assert late.job.vtime == pytest.approx(4.0)


async def test__enqueue__payload_roundtrips_as_json(pg_migrated_engine: AsyncEngine) -> None:
    queue = _queue(pg_migrated_engine)
    request = _request(uuid4())
    await queue.enqueue(request)

    job = await queue.get(request.job_id)

    assert job is not None
    assert job.payload == {"n": 1}
    assert job.queued_at.tzinfo is not None
    assert abs((datetime.now(UTC) - job.queued_at).total_seconds()) < 60


async def test__claim__query_plan__walks_partial_queue_index(pg_migrated_engine: AsyncEngine) -> None:
    stmt = PostgresJobQueue._best_candidate(_runner(), QueueQuota(max_running_per_user=2), datetime.now(UTC), LEASE_S)
    # Литерал ARRAY['tex'] имеет тип text[], в запросе приложения параметр приводится к колонке.
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    sql = sql.replace("ARRAY['tex']", "ARRAY['tex']::varchar[]")
    async with pg_migrated_engine.connect() as conn:
        await conn.execute(text("SET enable_seqscan = off"))
        plan = "\n".join(row[0] for row in await conn.execute(text(f"EXPLAIN {sql}")))

    assert "ix_jobs_queued_order" in plan
