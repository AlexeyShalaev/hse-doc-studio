"""Сценарии JobQueueService на поддельных часах: память и Postgres проходят одни и те же."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.jobs.enums import JobState, JobStatus, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import StaleAttemptError
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService

from tests.contract.base import PortContract
from tests.contract.test_job_queue_contract import LEASE_S, _Harness

if TYPE_CHECKING:
    from tests.fixtures.pg import PgDbFactory

GRACE_S = 15.0


class _Service(_Harness):
    def __init__(self, root: Path, queue: Callable[..., Any] | None = None) -> None:
        super().__init__(root, *([queue] if queue else []))
        self.service = JobQueueService(self.queue, lease_s=LEASE_S, timeout_grace_s=GRACE_S, clock=self.clock)


class TestJobQueueService(PortContract):
    implementations = {"inmemory": _Service}

    async def test__heartbeat__keeps_job_alive_past_original_lease(self, port: _Service) -> None:
        await port.put(uuid4())
        job = await port.claim()
        assert job is not None
        for _ in range(4):
            port.clock.advance(30)
            beat = await port.service.heartbeat(job.id, job.attempt)
            assert beat.cancel is False
            assert await port.service.reap() == ()
        current = await port.queue.get(job.id)
        assert current is not None
        assert current.state is JobState.running

    async def test__reap__silent_runner__requeues_then_fails_with_runner_lost(self, port: _Service) -> None:
        queued = await port.put(uuid4(), max_attempts=2)
        first = await port.claim()
        assert first is not None
        port.clock.advance(LEASE_S + 1)
        (outcome,) = await port.service.reap()
        assert (outcome.job.id, outcome.requeued, outcome.job.state) == (queued.id, True, JobState.queued)
        second = await port.claim()
        assert second is not None
        assert second.attempt == 2
        port.clock.advance(LEASE_S + 1)
        (lost,) = await port.service.reap()
        assert (lost.requeued, lost.job.state, lost.job.error_code) == (
            False,
            JobState.failed,
            RunnerErrorCode.runner_lost.value,
        )

    async def test__complete__stale_attempt__is_rejected_and_result_ignored(self, port: _Service) -> None:
        await port.put(uuid4(), max_attempts=2)
        first = await port.claim()
        assert first is not None
        port.clock.advance(LEASE_S + 1)
        await port.service.reap()
        second = await port.claim()
        assert second is not None
        with pytest.raises(StaleAttemptError):
            await port.service.complete(first.id, first.attempt, JobStatus.succeeded, result={"stale": True})
        done = await port.service.complete(second.id, second.attempt, JobStatus.succeeded, result={"ok": True})
        assert (done.state, done.result) == (JobState.succeeded, {"ok": True})

    async def test__cancel__queued_job__is_terminal_at_once(self, port: _Service) -> None:
        queued = await port.put(uuid4())
        cancelled = await port.service.cancel(queued.id)
        assert cancelled.state is JobState.cancelled
        assert await port.claim() is None

    async def test__cancel__running_job__is_delivered_by_heartbeat(self, port: _Service) -> None:
        await port.put(uuid4())
        job = await port.claim()
        assert job is not None
        await port.service.cancel(job.id)
        assert (await port.service.heartbeat(job.id, job.attempt)).cancel is True
        done = await port.service.complete(job.id, job.attempt, JobStatus.cancelled)
        assert done.state is JobState.cancelled

    async def test__timeouts__within_limit__does_nothing(self, port: _Service) -> None:
        await port.put(uuid4(), timeout_s=100.0)
        job = await port.claim()
        assert job is not None
        port.clock.advance(99)
        sweep = await port.service.enforce_timeouts()
        assert (sweep.cancelled, sweep.timed_out) == ((), ())

    async def test__timeouts__overdue__asks_runner_to_stop_via_heartbeat(self, port: _Service) -> None:
        await port.put(uuid4(), timeout_s=100.0)
        job = await port.claim()
        assert job is not None
        port.clock.advance(101)
        sweep = await port.service.enforce_timeouts()
        assert [j.id for j in sweep.cancelled] == [job.id]
        assert sweep.timed_out == ()
        beat = await port.service.heartbeat(job.id, job.attempt)
        assert beat.cancel is True
        # Повторный проход в пределах времени на остановку не дублирует отмену.
        assert (await port.service.enforce_timeouts()).cancelled == ()
        done = await port.service.complete(job.id, job.attempt, JobStatus.cancelled)
        assert done.state is JobState.timed_out

    async def test__timeouts__runner_ignores_cancel__server_finishes_job_as_timed_out(self, port: _Service) -> None:
        await port.put(uuid4(), timeout_s=100.0)
        job = await port.claim()
        assert job is not None
        port.clock.advance(101)
        await port.service.enforce_timeouts()
        port.clock.advance(GRACE_S)
        await port.service.heartbeat(job.id, job.attempt)
        sweep = await port.service.enforce_timeouts()
        assert [(j.id, j.state) for j in sweep.timed_out] == [(job.id, JobState.timed_out)]
        with pytest.raises(StaleAttemptError):
            await port.service.complete(job.id, job.attempt, JobStatus.succeeded)

    async def test__timeouts__retry_restarts_the_clock(self, port: _Service) -> None:
        await port.put(uuid4(), timeout_s=100.0, max_attempts=2)
        first = await port.claim()
        assert first is not None
        port.clock.advance(LEASE_S + 1)
        await port.service.reap()
        port.clock.advance(80)
        second = await port.claim()
        assert second is not None
        assert second.started_at == port.clock.now
        port.clock.advance(60)
        await port.service.heartbeat(second.id, second.attempt)
        sweep = await port.service.enforce_timeouts()
        assert (sweep.cancelled, sweep.timed_out) == ((), ())

    async def test__sweep__runs_reaper_and_timeouts_together(self, port: _Service) -> None:
        await port.put(uuid4(), timeout_s=1000.0)
        job = await port.claim()
        assert job is not None
        port.clock.advance(LEASE_S + 1)
        await port.service.sweep()
        current = await port.queue.get(job.id)
        assert current is not None
        assert current.state is JobState.failed


@pytest.mark.pg
class TestPostgresJobQueueService(TestJobQueueService):
    implementations: ClassVar[dict[str, Callable[..., Any]]] = {}

    @pytest_asyncio.fixture
    async def port(self, pg_db_factory: PgDbFactory) -> _Service:
        sessions = SessionProvider(create_sessionmaker(await pg_db_factory()))
        return _Service(Path(), lambda clock: PostgresJobQueue(sessions, clock))
