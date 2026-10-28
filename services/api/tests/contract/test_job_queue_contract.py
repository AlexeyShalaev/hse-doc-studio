"""Контрактный набор IJobQueue: порядок, справедливость, склейка, лимиты, аффинность, аренды и fencing.

Его проходят память и Postgres-очередь; для Postgres нужен `HSE_TEST_PG_DSN`, без него тесты пропускаются.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState, JobStatus
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError, StaleAttemptError
from hse_doc_studio.core.jobs.queue import EnqueueRequest, IJobQueue, QueuedJob, RunnerRef
from hse_doc_studio.core.jobs.scheduler import AFFINITY_WAIT, QueueQuota
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.session import SessionProvider

from tests.contract.base import PortContract
from tests.fakes.job_queue import InMemoryJobQueue

if TYPE_CHECKING:
    from tests.fixtures.pg import PgDbFactory

LEASE_S = 45.0


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


class _Harness:
    def __init__(self, _root: Path, queue: Callable[[FakeClock], IJobQueue] = InMemoryJobQueue) -> None:
        self.clock = FakeClock()
        self.queue: IJobQueue = queue(self.clock)
        self.runner = RunnerRef(id=uuid4(), tags=frozenset({"tex", "pack"}), concurrency=2)

    async def put(self, user: UUID, **kwargs: Any) -> QueuedJob:
        request = EnqueueRequest(
            job_id=kwargs.pop("job_id", uuid4()),
            kind=kwargs.pop("kind", JobKind.compile),
            project_id=kwargs.pop("project_id", uuid4()),
            user_id=user,
            tags=kwargs.pop("tags", frozenset({"tex"})),
            payload={},
            **kwargs,
        )
        return (await self.queue.enqueue(request)).job

    async def claim(self, runner: RunnerRef | None = None, quota: QueueQuota | None = None) -> QueuedJob | None:
        return await self.queue.claim(runner or self.runner, lease_s=LEASE_S, quota=quota)


_FACTORIES: dict[str, Callable[[Path], Any]] = {"inmemory": _Harness}


class TestJobQueueContract(PortContract):
    implementations = _FACTORIES

    async def test__claim__empty_queue__returns_none(self, port: _Harness) -> None:
        assert await port.claim() is None

    async def test__claim__takes_job_and_starts_first_attempt(self, port: _Harness) -> None:
        queued = await port.put(uuid4())
        taken = await port.claim()
        assert taken is not None
        assert (taken.id, taken.state, taken.attempt, taken.runner_id) == (
            queued.id,
            JobState.running,
            1,
            port.runner.id,
        )
        assert taken.lease_until == port.clock.now + timedelta(seconds=LEASE_S)
        assert await port.claim() is None

    async def test__claim__runner_without_tag__skips_job(self, port: _Harness) -> None:
        await port.put(uuid4(), tags=frozenset({"office"}))
        assert await port.claim() is None

    async def test__claim__interactive_class_beats_batch(self, port: _Harness) -> None:
        user = uuid4()
        batch = await port.put(user, kind=JobKind.pack_submission, priority_class=JobPriorityClass.batch)
        interactive = await port.put(uuid4(), priority_class=JobPriorityClass.interactive)
        first, second = await port.claim(), await port.claim()
        assert first is not None
        assert second is not None
        assert (first.id, second.id) == (interactive.id, batch.id)

    async def test__claim__fifteen_jobs_of_one_user_do_not_starve_a_newcomer(self, port: _Harness) -> None:
        bulk, newcomer = uuid4(), uuid4()
        for _ in range(15):
            await port.put(bulk)
        single = await port.put(newcomer)
        order = [(await port.claim()) for _ in range(3)]
        assert single.id in [job.id for job in order if job is not None][:2]

    async def test__claim__fair_share_alternates_users_with_equal_backlog(self, port: _Harness) -> None:
        first_user, second_user = uuid4(), uuid4()
        for _ in range(3):
            await port.put(first_user)
        for _ in range(3):
            await port.put(second_user)
        users = [job.user_id for job in [await port.claim() for _ in range(6)] if job is not None]
        assert users == [first_user, second_user] * 3

    async def test__claim__idle_user_gets_no_accumulated_credit(self, port: _Harness) -> None:
        busy, idle = uuid4(), uuid4()
        for _ in range(5):
            await port.put(busy)
        for _ in range(5):
            assert await port.claim() is not None
        # Глобальное время ушло вперёд: вернувшийся пользователь встаёт сразу за ним, а не в прошлое.
        for _ in range(3):
            await port.put(busy)
        late = await port.put(idle)
        assert late.vtime == pytest.approx(6.0)
        taken = await port.claim()
        assert taken is not None
        assert taken.vtime <= late.vtime

    async def test__claim__user_at_cap_is_skipped_but_others_run(self, port: _Harness) -> None:
        capped, other = uuid4(), uuid4()
        await port.put(capped)
        await port.put(capped)
        free = await port.put(other)
        quota = QueueQuota(max_running_per_user=1)
        first = await port.claim(quota=quota)
        second = await port.claim(quota=quota)
        assert first is not None
        assert first.user_id == capped
        assert second is not None
        assert second.id == free.id
        assert await port.claim(quota=quota) is None

    async def test__claim__org_cap_limits_members_together(self, port: _Harness) -> None:
        org = uuid4()
        await port.put(uuid4(), org_id=org)
        await port.put(uuid4(), org_id=org)
        quota = QueueQuota(max_running_per_org=1)
        assert await port.claim(quota=quota) is not None
        assert await port.claim(quota=quota) is None

    async def test__enqueue__same_coalesce_key__cancels_only_queued_job(self, port: _Harness) -> None:
        project = uuid4()
        running = await port.put(uuid4(), project_id=project, coalesce_key="doc")
        assert await port.claim() is not None
        queued = await port.put(uuid4(), project_id=project, coalesce_key="doc")
        outcome = await port.queue.enqueue(
            EnqueueRequest(
                job_id=uuid4(),
                kind=JobKind.compile,
                project_id=project,
                user_id=uuid4(),
                tags=frozenset({"tex"}),
                payload={},
                coalesce_key="doc",
            )
        )
        assert [job.id for job in outcome.superseded] == [queued.id]
        assert outcome.superseded[0].state is JobState.cancelled
        assert outcome.superseded[0].error_code == "superseded"
        current = await port.queue.get(running.id)
        assert current is not None
        assert current.state is JobState.running

    async def test__enqueue__other_coalesce_key__keeps_queued_job(self, port: _Harness) -> None:
        await port.put(uuid4(), coalesce_key="a")
        outcome = await port.queue.enqueue(
            EnqueueRequest(
                job_id=uuid4(),
                kind=JobKind.compile,
                project_id=uuid4(),
                user_id=uuid4(),
                tags=frozenset({"tex"}),
                payload={},
                coalesce_key="b",
            )
        )
        assert outcome.superseded == ()

    async def test__claim__affine_runner_has_priority_for_two_seconds(self, port: _Harness) -> None:
        warm = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1)
        other = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1)
        await port.claim(warm)
        job = await port.put(uuid4(), affinity_runner_id=warm.id)
        assert await port.claim(other) is None
        port.clock.advance(AFFINITY_WAIT.total_seconds() - 0.5)
        assert await port.claim(other) is None
        port.clock.advance(0.5)
        taken = await port.claim(other)
        assert taken is not None
        assert taken.id == job.id

    async def test__claim__affine_runner_never_seen__does_not_block_others(self, port: _Harness) -> None:
        await port.put(uuid4(), affinity_runner_id=uuid4())
        assert await port.claim() is not None

    async def test__claim__affine_runner_at_capacity__does_not_block_others(self, port: _Harness) -> None:
        warm = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1)
        other = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1)
        await port.put(uuid4())
        assert await port.claim(warm) is not None
        await port.put(uuid4(), affinity_runner_id=warm.id)
        assert await port.claim(other) is not None

    async def test__claim__affine_runner_silent_past_lease__does_not_block_others(self, port: _Harness) -> None:
        warm = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1)
        other = RunnerRef(id=uuid4(), tags=frozenset({"tex"}), concurrency=1)
        await port.claim(warm)
        port.clock.advance(LEASE_S + 1)
        await port.put(uuid4(), affinity_runner_id=warm.id)
        assert await port.claim(other) is not None

    async def test__heartbeat__extends_lease_and_reports_cancel(self, port: _Harness) -> None:
        await port.put(uuid4())
        job = await port.claim()
        assert job is not None
        port.clock.advance(10)
        beat = await port.queue.heartbeat(job.id, job.attempt, lease_s=LEASE_S)
        assert beat.cancel is False
        assert beat.lease_until == port.clock.now + timedelta(seconds=LEASE_S)
        await port.queue.request_cancel(job.id)
        assert (await port.queue.heartbeat(job.id, job.attempt, lease_s=LEASE_S)).cancel is True

    async def test__complete__finishes_job_with_result(self, port: _Harness) -> None:
        await port.put(uuid4())
        job = await port.claim()
        assert job is not None
        done = await port.queue.complete(job.id, job.attempt, JobStatus.succeeded, result={"ok": True})
        assert (done.state, done.result, done.lease_until) == (JobState.succeeded, {"ok": True}, None)
        assert done.finished_at == port.clock.now

    async def test__complete__stale_attempt_after_requeue__is_rejected(self, port: _Harness) -> None:
        await port.put(uuid4(), max_attempts=2)
        first = await port.claim()
        assert first is not None
        port.clock.advance(LEASE_S + 1)
        await port.queue.requeue_expired()
        second = await port.claim()
        assert second is not None
        assert second.attempt == 2
        with pytest.raises(StaleAttemptError):
            await port.queue.complete(first.id, first.attempt, JobStatus.succeeded)
        with pytest.raises(StaleAttemptError):
            await port.queue.heartbeat(first.id, first.attempt, lease_s=LEASE_S)
        done = await port.queue.complete(second.id, second.attempt, JobStatus.succeeded)
        assert done.state is JobState.succeeded

    async def test__complete__twice__second_is_stale(self, port: _Harness) -> None:
        await port.put(uuid4())
        job = await port.claim()
        assert job is not None
        await port.queue.complete(job.id, job.attempt, JobStatus.failed, error_code="boom")
        with pytest.raises(StaleAttemptError):
            await port.queue.complete(job.id, job.attempt, JobStatus.succeeded)

    async def test__requeue_expired__live_lease__keeps_job_running(self, port: _Harness) -> None:
        await port.put(uuid4())
        await port.claim()
        port.clock.advance(LEASE_S - 1)
        assert await port.queue.requeue_expired() == ()

    async def test__requeue_expired__attempts_left__returns_job_to_queue_in_place(self, port: _Harness) -> None:
        queued = await port.put(uuid4(), max_attempts=2)
        await port.claim()
        port.clock.advance(LEASE_S + 1)
        (outcome,) = await port.queue.requeue_expired()
        assert outcome.requeued is True
        assert (outcome.job.state, outcome.job.runner_id, outcome.job.vtime) == (
            JobState.queued,
            None,
            queued.vtime,
        )

    async def test__requeue_expired__attempts_exhausted__fails_with_runner_lost(self, port: _Harness) -> None:
        await port.put(uuid4(), max_attempts=1)
        await port.claim()
        port.clock.advance(LEASE_S + 1)
        (outcome,) = await port.queue.requeue_expired()
        assert outcome.requeued is False
        assert (outcome.job.state, outcome.job.error_code) == (JobState.failed, "runner_lost")

    async def test__request_cancel__queued_job__is_cancelled_at_once(self, port: _Harness) -> None:
        queued = await port.put(uuid4())
        cancelled = await port.queue.request_cancel(queued.id)
        assert cancelled.state is JobState.cancelled
        assert await port.claim() is None

    async def test__request_cancel__running_job__sets_flag_only(self, port: _Harness) -> None:
        await port.put(uuid4())
        job = await port.claim()
        assert job is not None
        flagged = await port.queue.request_cancel(job.id)
        assert (flagged.state, flagged.cancel_requested) == (JobState.running, True)

    async def test__request_cancel__unknown_job__raises(self, port: _Harness) -> None:
        with pytest.raises(QueuedJobNotFoundError):
            await port.queue.request_cancel(uuid4())

    async def test__list__filters_by_state_and_project(self, port: _Harness) -> None:
        project = uuid4()
        mine = await port.put(uuid4(), project_id=project)
        await port.put(uuid4())
        assert [j.id for j in await port.queue.list(project_id=project)] == [mine.id]
        assert len(await port.queue.list(state=JobState.queued)) == 2
        assert await port.queue.list(state=JobState.running) == ()


@pytest.mark.pg
class TestPostgresJobQueueContract(TestJobQueueContract):
    # Свой async-фикстуры `port`: пустой реестр не даёт базовому классу подменить её.
    implementations: ClassVar[dict[str, Callable[..., Any]]] = {}

    @pytest_asyncio.fixture
    async def port(self, pg_db_factory: PgDbFactory) -> _Harness:
        sessions = SessionProvider(create_sessionmaker(await pg_db_factory()))
        return _Harness(Path(), lambda clock: PostgresJobQueue(sessions, clock))
