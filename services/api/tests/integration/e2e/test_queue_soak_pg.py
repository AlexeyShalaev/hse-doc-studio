"""Soak очереди на настоящем Postgres: 200 задач, случайные сбои раннеров, ни дублей, ни потерь.

Часы управляемые: раунд раннеров, затем время прыгает за аренду и сборщик возвращает брошенные задачи.
Генератор случайных чисел с фиксированным зерном, поэтому прогон воспроизводим.
"""

from __future__ import annotations

import asyncio
import random
from collections import Counter
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobState, JobStatus, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import StaleAttemptError
from hse_doc_studio.core.jobs.queue import EnqueueRequest, QueuedJob, RunnerRef
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.repositories.jobs_applied import SqlJobApplyLedger
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

JOBS = 200
USERS = 12
RUNNERS = 8
LEASE_S = 45.0
MAX_ATTEMPTS = 3
MAX_ROUNDS = 60


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _Ledger:
    """Что видели раннеры: сколько раз задача закрыта успешно и какие закрытия отвергнуты как устаревшие."""

    def __init__(self) -> None:
        self.completed: Counter[UUID] = Counter()
        self.rejected: Counter[UUID] = Counter()
        self.crashed: list[QueuedJob] = []


async def _worker(queue: PostgresJobQueue, rng: random.Random, seen: _Ledger) -> None:
    runner = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1)
    while (job := await queue.claim(runner, lease_s=LEASE_S)) is not None:
        roll = rng.random()
        if roll < 0.12:
            # Раннер пропал: не закрывает и не продлевает аренду.
            seen.crashed.append(job)
            continue
        status = JobStatus.succeeded if roll < 0.82 else JobStatus.failed
        await queue.complete(job.id, job.attempt, status, error_code=None if status is JobStatus.succeeded else "boom")
        seen.completed[job.id] += 1


async def _late_completions(queue: PostgresJobQueue, seen: _Ledger) -> None:
    """Вернувшийся раннер пытается закрыть попытку, которую уже отобрали: так закрыть нельзя."""
    for job in seen.crashed:
        try:
            await queue.complete(job.id, job.attempt, JobStatus.succeeded)
        except StaleAttemptError:
            seen.rejected[job.id] += 1
        else:
            seen.completed[job.id] += 1
    seen.crashed.clear()


async def test__soak__two_hundred_jobs_with_random_failures__no_double_completion_no_lost_job(
    pg_migrated_engine: AsyncEngine,
) -> None:
    clock = _Clock()
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    queue, ledger = PostgresJobQueue(sessions, clock), SqlJobApplyLedger(sessions, clock)
    rng = random.Random(20261030)  # noqa: S311 — детерминированное зерно теста
    users = [uuid4() for _ in range(USERS)]
    ids = [uuid4() for _ in range(JOBS)]
    for job_id in ids:
        await queue.enqueue(
            EnqueueRequest(
                job_id=job_id,
                kind=JobKind.compile,
                project_id=uuid4(),
                user_id=rng.choice(users),
                tags=frozenset({"tex"}),
                payload={},
                max_attempts=MAX_ATTEMPTS,
            )
        )
    seen = _Ledger()

    for _ in range(MAX_ROUNDS):
        await asyncio.gather(*(_worker(queue, rng, seen) for _ in range(RUNNERS)))
        clock.advance(LEASE_S + 1)
        await queue.requeue_expired()
        await _late_completions(queue, seen)
        if not await queue.list(state=JobState.queued) and not await queue.list(state=JobState.running):
            break

    jobs = {job.id: job for job in await queue.list()}
    assert set(jobs) == set(ids)
    assert all(job.state.is_terminal for job in jobs.values()), "задача потеряна: не дошла до конечного состояния"
    assert max(seen.completed.values()) == 1, "задача закрыта дважды"
    assert all(job.attempt <= MAX_ATTEMPTS for job in jobs.values())
    lost = [job for job in jobs.values() if job.error_code == RunnerErrorCode.runner_lost.value]
    assert {job.id for job in lost}.isdisjoint(seen.completed), "потерянная попытка не должна иметь закрытия"
    assert set(seen.completed) | {job.id for job in lost} == set(ids)
    assert sum(seen.rejected.values()) > 0, "сценарий не дошёл до устаревших закрытий"
    assert any(job.attempt > 1 for job in jobs.values()), "сценарий не вернул ни одной брошенной задачи в очередь"

    # Применение итогов: каждый итог ставит метку ровно один раз, сколько бы применяющих ни гонялось.
    first = await asyncio.gather(*(ledger.mark_applied(job_id) for job_id in ids for _ in range(3)))
    assert sum(first) == JOBS
    assert await ledger.list_unapplied() == ()
