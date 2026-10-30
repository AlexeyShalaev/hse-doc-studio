"""Postgres-очередь задач: параллельные раннеры, лимиты под гонкой, состояние справедливости и план запроса."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import EnqueueRequest, QueuedJob, RunnerRef
from hse_doc_studio.core.jobs.quotas import QuotaOverride, QuotaOwnerKind, QuotaResource
from hse_doc_studio.core.jobs.routing import JobRoute, RunnerScope
from hse_doc_studio.core.jobs.scheduler import QueueQuota
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.job_quotas import SqlProjectOrgReader, SqlQuotaOverrideRepository
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.factories.pg_projects import seed_project, seed_user

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


async def test__claim__per_owner_caps__capped_user_skipped_others_served(pg_migrated_engine: AsyncEngine) -> None:
    queue = _queue(pg_migrated_engine)
    org, strict, roomy = uuid4(), uuid4(), uuid4()
    for user in (strict, strict, roomy, roomy):
        await queue.enqueue(_request(user, org_id=org))
    quota = QueueQuota(max_running_per_user=1, user_caps={roomy: 2}, org_caps={org: 3})

    taken: list[QueuedJob] = []
    while (job := await queue.claim(_runner(), lease_s=LEASE_S, quota=quota)) is not None:
        taken.append(job)

    assert sorted(job.user_id == roomy for job in taken) == [False, True, True]
    assert len(taken) == 3


async def test__quota_overrides__roundtrip_and_project_org(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    repo = SqlQuotaOverrideRepository(sessions)
    user = str(uuid4())
    await repo.set(QuotaOverride(QuotaOwnerKind.user, user, QuotaResource.concurrent_user, 2))
    await repo.set(QuotaOverride(QuotaOwnerKind.user, user, QuotaResource.concurrent_user, 3))
    await repo.set(QuotaOverride(QuotaOwnerKind.org, "hse", QuotaResource.max_duration_s, 90))

    assert {(o.owner_id, o.resource, o.hard_limit) for o in await repo.list_all()} == {
        (user, QuotaResource.concurrent_user, 3),
        ("hse", QuotaResource.max_duration_s, 90),
    }

    await repo.delete(QuotaOwnerKind.user, user, QuotaResource.concurrent_user)
    assert [o.owner_id for o in await repo.list_all()] == ["hse"]
    assert await SqlProjectOrgReader(sessions).org_of(uuid4()) is None


async def _personal_job(engine: AsyncEngine, queue: PostgresJobQueue, until: datetime) -> tuple[UUID, QueuedJob]:
    sessions = SessionProvider(create_sessionmaker(engine))
    owner = UUID(await seed_user(sessions))
    project = await seed_project(sessions, owner_user_id=str(owner))
    outcome = await queue.enqueue(
        EnqueueRequest(
            job_id=uuid4(),
            kind=JobKind.compile,
            project_id=project,
            user_id=owner,
            tags=frozenset({"tex"}),
            payload={},
            route=JobRoute.personal_first,
            route_owner_id=str(owner),
            personal_until=until,
        )
    )
    return owner, outcome.job


async def test__claim__personal_and_shared_race_at_window_edge__exactly_one_takes(
    pg_migrated_engine: AsyncEngine,
) -> None:
    queue = _queue(pg_migrated_engine)
    # Окно уже закрыто: задачу могут взять и личный, и общий раннер, но только один из них.
    owner, job = await _personal_job(pg_migrated_engine, queue, datetime.now(UTC))
    personal = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), scope=RunnerScope.personal, owner_id=str(owner))
    claimers = [personal, *(_runner() for _ in range(5))]

    results = await asyncio.gather(*(queue.claim(r, lease_s=LEASE_S) for r in claimers))

    taken = [r for r in results if r is not None]
    assert [r.id for r in taken] == [job.id]


async def test__claim__personal_runner_does_not_wait_for_the_quota_lock(pg_migrated_engine: AsyncEngine) -> None:
    queue = _queue(pg_migrated_engine)
    owner, job = await _personal_job(pg_migrated_engine, queue, datetime(2100, 1, 1, tzinfo=UTC))
    personal = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), scope=RunnerScope.personal, owner_id=str(owner))
    holder_engine = pg_migrated_engine
    async with holder_engine.connect() as holder:
        transaction = await holder.begin()
        await holder.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 0x4A4F4253})
        try:
            taken = await asyncio.wait_for(
                queue.claim(personal, lease_s=LEASE_S, quota=QueueQuota(max_running_per_user=1)), timeout=5
            )
        finally:
            await transaction.rollback()
    assert taken is not None
    assert taken.id == job.id
