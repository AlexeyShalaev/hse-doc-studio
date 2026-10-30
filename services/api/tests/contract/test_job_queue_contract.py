"""Контрактный набор IJobQueue: порядок, справедливость, склейка, лимиты, аффинность, аренды и fencing.

Его проходят память и Postgres-очередь; для Postgres нужен `HSE_TEST_PG_DSN`, без него тесты пропускаются.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState, JobStatus
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError, StaleAttemptError
from hse_doc_studio.core.jobs.queue import EnqueueRequest, IJobQueue, QueuedJob, RunnerRef
from hse_doc_studio.core.jobs.routing import (
    JobRoute,
    ProjectBuildRunners,
    ProjectRouteInfo,
    RouteReason,
    RunnerScope,
)
from hse_doc_studio.core.jobs.scheduler import AFFINITY_WAIT, QueueQuota
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.session import SessionProvider

from tests.contract.base import PortContract
from tests.factories.pg_projects import seed_project, seed_user
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
    def __init__(
        self,
        _root: Path,
        queue: Callable[[FakeClock], IJobQueue] = InMemoryJobQueue,
        sessions: SessionProvider | None = None,
    ) -> None:
        self.clock = FakeClock()
        self.queue: IJobQueue = queue(self.clock)
        self.runner = RunnerRef(id=uuid4(), tags=frozenset({"tex", "pack"}), concurrency=2)
        self._sessions = sessions

    async def project(
        self, owner: UUID | None, policy: ProjectBuildRunners = ProjectBuildRunners.shared, *, deleted: bool = False
    ) -> UUID:
        """Проект в каталоге: у Postgres строка projects (и владелец в users), у памяти запись фейка."""
        if self._sessions is not None:
            if owner is not None:
                await seed_user(self._sessions, str(owner))
            return await seed_project(
                self._sessions,
                owner_user_id=str(owner) if owner is not None else None,
                build_runners=policy.value,
                deleted=deleted,
            )
        project_id = uuid4()
        assert isinstance(self.queue, InMemoryJobQueue)
        self.queue.set_project(
            ProjectRouteInfo(
                project_id=project_id,
                owner_user_id=str(owner) if owner is not None else None,
                owner_org_id=None,
                build_runners=policy,
                deleted=deleted,
            )
        )
        return project_id

    async def set_policy(self, project_id: UUID, policy: ProjectBuildRunners) -> None:
        if self._sessions is not None:
            from hse_doc_studio.infra.db.repositories.project_route_policy import SqlProjectRoutePolicyRepository

            await SqlProjectRoutePolicyRepository(self._sessions).set_build_runners(project_id, policy)
            return
        assert isinstance(self.queue, InMemoryJobQueue)
        info = self.queue._projects[project_id]
        self.queue.set_project(replace(info, build_runners=policy))

    async def put_personal(
        self, owner: UUID, project_id: UUID, *, user: UUID | None = None, **kwargs: Any
    ) -> QueuedJob:
        return await self.put(
            user or owner,
            project_id=project_id,
            route=JobRoute.personal_first,
            route_owner_id=str(owner),
            personal_until=self.clock.now + timedelta(seconds=5),
            route_reason=RouteReason.waiting_personal,
            **kwargs,
        )

    def personal(self, owner: UUID, *, accept_jobs: bool = True, accept_relay: bool = True) -> RunnerRef:
        return RunnerRef(
            id=uuid4(),
            tags=frozenset({"tex", "pack", "ai", "verify"}),
            scope=RunnerScope.personal,
            owner_id=str(owner),
            accept_jobs=accept_jobs,
            accept_relay=accept_relay,
        )

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
        assert taken.started_at == port.clock.now
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

    async def test__claim__user_override_beats_org_and_installation(self, port: _Harness) -> None:
        org, strict, roomy, member = uuid4(), uuid4(), uuid4(), uuid4()
        for user in (strict, strict, roomy, roomy, roomy, member, member):
            await port.put(user, org_id=org)
        quota = QueueQuota(
            max_running_per_user=2,
            user_caps={strict: 1, roomy: 3},
            org_user_caps={org: 1},
        )
        taken: list[QueuedJob] = []
        while (job := await port.claim(quota=quota)) is not None:
            taken.append(job)
        by_user = {user: sum(1 for job in taken if job.user_id == user) for user in (strict, roomy, member)}
        assert by_user == {strict: 1, roomy: 3, member: 1}

    async def test__claim__org_override_does_not_block_other_orgs(self, port: _Harness) -> None:
        capped, free = uuid4(), uuid4()
        await port.put(uuid4(), org_id=capped)
        await port.put(uuid4(), org_id=capped)
        later = await port.put(uuid4(), org_id=free)
        quota = QueueQuota(max_running_per_org=5, org_caps={capped: 1})
        first = await port.claim(quota=quota)
        second = await port.claim(quota=quota)
        assert first is not None
        assert first.org_id == capped
        assert second is not None
        assert second.id == later.id
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

    async def test__enqueue__same_coalesce_key__asks_running_job_to_stop(self, port: _Harness) -> None:
        project = uuid4()
        running = await port.put(uuid4(), project_id=project, coalesce_key="doc")
        assert await port.claim() is not None
        await port.put(uuid4(), project_id=project, coalesce_key="doc")
        current = await port.queue.get(running.id)
        assert current is not None
        assert (current.state, current.cancel_requested) == (JobState.running, True)

    async def test__complete__succeeded_after_cancel_request__is_stored_as_cancelled(self, port: _Harness) -> None:
        await port.put(uuid4())
        job = await port.claim()
        assert job is not None
        await port.queue.request_cancel(job.id)
        done = await port.queue.complete(job.id, job.attempt, JobStatus.succeeded, result={"ok": True})
        assert (done.state, done.result, done.error_code) == (JobState.cancelled, None, None)

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

    # Личные раннеры: матрица выдачи Q1–Q12 спецификации.

    async def test__personal__q1_owner_job__personal_in_window_shared_after_with_timeout(self, port: _Harness) -> None:
        owner = uuid4()
        project = await port.project(owner)
        job = await port.put_personal(owner, project)
        assert await port.claim() is None
        taken = await port.claim(port.personal(owner))
        assert taken is not None
        assert (taken.id, taken.runner_scope, taken.route_reason) == (
            job.id,
            RunnerScope.personal,
            RouteReason.personal,
        )

        late = await port.put_personal(owner, project)
        port.clock.advance(5)
        shared = await port.claim()
        assert shared is not None
        assert (shared.id, shared.runner_scope, shared.route_reason) == (
            late.id,
            RunnerScope.shared,
            RouteReason.fallback_timeout,
        )

    async def test__personal__q2_coauthor_follows_project_policy(self, port: _Harness) -> None:
        owner, coauthor = uuid4(), uuid4()
        project = await port.project(owner)
        await port.put_personal(owner, project, user=coauthor)
        assert await port.claim(port.personal(owner)) is None
        await port.set_policy(project, ProjectBuildRunners.owner)
        taken = await port.claim(port.personal(owner))
        assert taken is not None
        assert taken.user_id == coauthor

    async def test__personal__q3_stranger_runner_never_sees_the_job(self, port: _Harness) -> None:
        owner, stranger = uuid4(), uuid4()
        project = await port.project(owner, ProjectBuildRunners.owner)
        await port.put_personal(owner, project)
        assert await port.claim(port.personal(stranger)) is None
        port.clock.advance(10)
        assert await port.claim(port.personal(stranger)) is None

    async def test__personal__q4_personal_jobs_do_not_use_the_user_quota(self, port: _Harness) -> None:
        owner = uuid4()
        project = await port.project(owner)
        quota = QueueQuota(max_running_per_user=1)
        await port.put_personal(owner, project)
        assert await port.claim(port.personal(owner)) is not None
        shared_job = await port.put(owner)
        taken = await port.claim(quota=quota)
        assert taken is not None
        assert taken.id == shared_job.id
        await port.put(owner)
        assert await port.claim(quota=quota) is None

    async def test__personal__q5_personal_claims_refund_the_fair_share(self, port: _Harness) -> None:
        owner, other = uuid4(), uuid4()
        project = await port.project(owner)
        for _ in range(15):
            await port.put_personal(owner, project)
        runner = port.personal(owner)
        for _ in range(15):
            assert await port.claim(runner) is not None
        await port.put(other)
        await port.put(other)
        mine = await port.put(owner)
        order = [await port.claim() for _ in range(3)]
        assert [job.id for job in order if job is not None].index(mine.id) <= 1

    async def test__personal__q5_refund_happens_once_per_job(self, port: _Harness) -> None:
        owner = uuid4()
        project = await port.project(owner)
        queued = await port.put_personal(owner, project, max_attempts=3)
        runner = port.personal(owner)
        first = await port.claim(runner)
        port.clock.advance(LEASE_S + 1)
        await port.queue.requeue_expired()
        second = await port.claim(runner)
        assert queued.vcost == 1.0
        assert first is not None
        assert second is not None
        # Метка возвращена при первой выдаче; повторная выдача и повтор на общем раннере ничего не вернут.
        assert (first.vcost, second.vcost) == (0.0, 0.0)

    async def test__personal__q6_lost_personal_attempt_retries_anywhere(self, port: _Harness) -> None:
        owner = uuid4()
        project = await port.project(owner)
        await port.put_personal(owner, project, max_attempts=2, timeout_s=300.0, timeout_personal_s=600.0)
        taken = await port.claim(port.personal(owner))
        assert taken is not None
        assert taken.timeout_s == 600.0
        port.clock.advance(LEASE_S + 1)
        (outcome,) = await port.queue.requeue_expired()
        assert outcome.requeued is True
        assert (
            outcome.job.runner_scope,
            outcome.job.route_reason,
            outcome.job.personal_until,
            outcome.job.timeout_s,
        ) == (
            None,
            RouteReason.fallback_lost,
            port.clock.now,
            300.0,
        )
        again = await port.claim()
        assert again is not None
        assert (again.runner_scope, again.route_reason) == (RunnerScope.shared, RouteReason.fallback_lost)

    async def test__personal__q7_signature_check_never_goes_personal(self, port: _Harness) -> None:
        owner = uuid4()
        project = await port.project(owner)
        await port.put_personal(owner, project, kind=JobKind.verify_detached, tags=frozenset({"verify"}))
        assert await port.claim(port.personal(owner)) is None

    async def test__personal__q8_owner_change_or_policy_change_after_enqueue(self, port: _Harness) -> None:
        owner, coauthor = uuid4(), uuid4()
        project = await port.project(owner, ProjectBuildRunners.owner)
        await port.put_personal(owner, project, user=coauthor)
        await port.set_policy(project, ProjectBuildRunners.shared)
        assert await port.claim(port.personal(owner)) is None
        other_owner = uuid4()
        foreign = await port.project(other_owner)
        # Запись маршрута говорит «владелец owner», а проект теперь чужой: личный раннер не берёт.
        await port.put_personal(owner, foreign)
        assert await port.claim(port.personal(owner)) is None

    async def test__personal__q9_pinned_only_for_target_runner_of_its_owner(self, port: _Harness) -> None:
        owner = uuid4()
        runner = port.personal(owner)
        pinned = await port.put(
            owner,
            kind=JobKind.ai_relay,
            tags=frozenset({"ai"}),
            route=JobRoute.pinned,
            target_runner_id=runner.id,
            fair_share=False,
        )
        assert await port.claim(RunnerRef(id=uuid4(), tags=frozenset({"ai"}))) is None
        assert await port.claim(port.personal(owner)) is None
        assert await port.claim(RunnerRef(**{**runner.__dict__, "owner_id": str(uuid4())})) is None
        taken = await port.claim(runner)
        assert taken is not None
        assert (taken.id, taken.route_reason, taken.runner_scope) == (
            pinned.id,
            RouteReason.pinned,
            RunnerScope.personal,
        )

    async def test__personal__q9_pinned_of_another_user_is_not_taken(self, port: _Harness) -> None:
        owner = uuid4()
        runner = port.personal(owner)
        await port.put(
            uuid4(),
            kind=JobKind.ai_relay,
            tags=frozenset({"ai"}),
            route=JobRoute.pinned,
            target_runner_id=runner.id,
            fair_share=False,
        )
        assert await port.claim(runner) is None

    async def test__personal__q10_slot_flags_split_builds_and_relays(self, port: _Harness) -> None:
        owner = uuid4()
        project = await port.project(owner)
        relay_runner = port.personal(owner, accept_jobs=False)
        build = await port.put_personal(owner, project)
        relay = await port.put(
            owner,
            kind=JobKind.ai_relay,
            tags=frozenset({"ai"}),
            route=JobRoute.pinned,
            target_runner_id=relay_runner.id,
            fair_share=False,
        )
        no_relay = RunnerRef(**{**relay_runner.__dict__, "accept_jobs": True, "accept_relay": False})
        taken_relay = await port.claim(relay_runner)
        assert taken_relay is not None
        assert taken_relay.id == relay.id
        taken_build = await port.claim(no_relay)
        assert taken_build is not None
        assert taken_build.id == build.id

    async def test__personal__q11_policy_shared_expires_only_coauthor_builds(self, port: _Harness) -> None:
        owner, coauthor = uuid4(), uuid4()
        project = await port.project(owner, ProjectBuildRunners.owner)
        own = await port.put_personal(owner, project)
        theirs = await port.put_personal(owner, project, user=coauthor)
        await port.set_policy(project, ProjectBuildRunners.shared)
        expired = await port.queue.expire_personal_wait(
            project_id=project, reason=RouteReason.policy_shared, coauthors_only=True
        )
        assert expired == 1
        taken = await port.claim()
        assert taken is not None
        # Общий раннер оставляет причину переключения политики, а не «не дождались 5 с».
        assert (taken.id, taken.route_reason) == (theirs.id, RouteReason.policy_shared)
        assert await port.claim() is None
        mine = await port.claim(port.personal(owner))
        assert mine is not None
        assert mine.id == own.id

    async def test__personal__q11_expire_wait_and_cancel_pinned(self, port: _Harness) -> None:
        anna, boris = uuid4(), uuid4()
        anna_project, boris_project = await port.project(anna), await port.project(boris)
        await port.put_personal(anna, anna_project)
        boris_job = await port.put_personal(boris, boris_project)
        assert await port.queue.expire_personal_wait(owner_id=str(anna)) == 1
        anna_taken = await port.claim()
        assert anna_taken is not None
        assert anna_taken.route_reason is RouteReason.fallback_offline
        assert await port.claim() is None
        assert await port.queue.expire_personal_wait(project_id=boris_project, reason=RouteReason.disabled) == 1
        boris_taken = await port.claim()
        assert boris_taken is not None
        assert (boris_taken.id, boris_taken.route_reason) == (boris_job.id, RouteReason.disabled)
        assert await port.queue.expire_personal_wait() == 0

        target = uuid4()
        relay = await port.put(
            anna, kind=JobKind.ai_relay, tags=frozenset({"ai"}), route=JobRoute.pinned, target_runner_id=target
        )
        assert await port.queue.cancel_pinned(runner_id=uuid4(), error_code="relay_unavailable") == ()
        (cancelled,) = await port.queue.cancel_pinned(runner_id=None, error_code="relay_unavailable")
        assert (cancelled.id, cancelled.state, cancelled.error_code) == (
            relay.id,
            JobState.cancelled,
            "relay_unavailable",
        )

    async def test__personal__q12_deleted_project_is_not_built_personally(self, port: _Harness) -> None:
        owner = uuid4()
        project = await port.project(owner, deleted=True)
        await port.put_personal(owner, project)
        assert await port.claim(port.personal(owner)) is None

    async def test__personal__unfair_relay_keeps_the_user_mark(self, port: _Harness) -> None:
        owner = uuid4()
        relay = await port.put(
            owner,
            kind=JobKind.ai_relay,
            tags=frozenset({"ai"}),
            route=JobRoute.pinned,
            target_runner_id=uuid4(),
            fair_share=False,
        )
        build = await port.put(owner)
        assert (relay.vcost, relay.vtime) == (0.0, 0.0)
        assert build.vtime == pytest.approx(1.0)

    async def test__personal__shared_runner_without_free_build_slots_takes_nothing(self, port: _Harness) -> None:
        await port.put(uuid4())
        assert await port.claim(RunnerRef(id=uuid4(), tags=frozenset({"tex"}), accept_jobs=False)) is None


@pytest.mark.pg
class TestPostgresJobQueueContract(TestJobQueueContract):
    # Свой async-фикстуры `port`: пустой реестр не даёт базовому классу подменить её.
    implementations: ClassVar[dict[str, Callable[..., Any]]] = {}

    @pytest_asyncio.fixture
    async def port(self, pg_db_factory: PgDbFactory) -> _Harness:
        sessions = SessionProvider(create_sessionmaker(await pg_db_factory()))
        return _Harness(Path(), lambda clock: PostgresJobQueue(sessions, clock), sessions)
