"""Метрики общего пула в Postgres: ждущие задачи, возраст самой старой, живые общие раннеры и слоты."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.queue import EnqueueRequest, RunnerRef
from hse_doc_studio.core.jobs.routing import JobRoute
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.repositories.queue_metrics import SqlQueueMetricsReader
from hse_doc_studio.infra.db.repositories.runners import SqlRunnerRepository
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

NOW = datetime.now(UTC)


def _runner(name: str, *, seen: timedelta | None, concurrency: int = 2, **kwargs: object) -> Runner:
    return Runner(
        id=uuid4().hex,
        name=name,
        token_hash=uuid4().hex + uuid4().hex,
        tags=frozenset({"tex"}),
        concurrency=concurrency,
        resource_class="std",
        version="1",
        created_at=NOW,
        last_seen_at=NOW - seen if seen is not None else None,
        **kwargs,  # type: ignore[arg-type]
    )


def _job(**kwargs: object) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=uuid4(),
        kind=JobKind.compile,
        project_id=uuid4(),
        user_id=uuid4(),
        tags=frozenset({"tex"}),
        payload={},
        **kwargs,  # type: ignore[arg-type]
    )


async def test__read__counts_only_the_shared_pool(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    queue, runners = PostgresJobQueue(sessions), SqlRunnerRepository(sessions)
    for item in (
        _runner("live-a", seen=timedelta(seconds=5)),
        _runner("live-b", seen=timedelta(seconds=30), concurrency=3),
        _runner("silent", seen=timedelta(minutes=10)),
        _runner("paused", seen=timedelta(seconds=5), paused=True),
        _runner("revoked", seen=timedelta(seconds=5), revoked_at=NOW),
        _runner("goodbye", seen=timedelta(seconds=5), offline_at=NOW),
    ):
        await runners.add(item)

    await queue.enqueue(_job())
    await queue.enqueue(_job())
    await queue.enqueue(
        _job(route=JobRoute.personal_first, route_owner_id=uuid4().hex, personal_until=NOW + timedelta(seconds=30))
    )
    await queue.enqueue(_job())
    await queue.claim(RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1), lease_s=45.0)

    metrics = await SqlQueueMetricsReader(sessions).read(datetime.now(UTC) + timedelta(seconds=3))

    assert (metrics.runners_online, metrics.slots_total) == (2, 5)
    assert metrics.running == 1
    assert metrics.queued == 2
    assert metrics.oldest_wait_s >= 3
