"""Опрос личного раннера: область из записи, слоты, урезанный актор, таймаут из записи, выключение."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.jobs.codec import encode_envelope
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.core.jobs.routing import (
    JobRoute,
    PersonalRunnerSettings,
    ProjectBuildRunners,
    ProjectRouteInfo,
    RunnerScope,
)
from hse_doc_studio.core.jobs.runners import JobTokenSigner, Runner, RunnerOwnerKind
from hse_doc_studio.core.jobs.wire import JobEnvelope, PollRequest
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

from tests.fakes.identity import InMemoryUserRepository
from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRunnerRepository
from tests.unit.core.jobs.samples import make_compile_spec

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


class _Settings:
    def __init__(self) -> None:
        self.value = PersonalRunnerSettings()

    async def current(self) -> PersonalRunnerSettings:
        return self.value


async def _world(
    *, users: InMemoryUserRepository | None = None, runners: InMemoryRunnerRepository | None = None
) -> tuple[RunnerJobService, InMemoryJobQueue, Runner, _Settings, UUID]:
    queue = InMemoryJobQueue(clock=lambda: NOW)
    runners = runners or InMemoryRunnerRepository()
    settings = _Settings()
    owner = uuid4()
    runner = Runner(
        id=uuid4().hex,
        name="MacBook",
        token_hash="h",
        tags=frozenset({"tex"}),
        concurrency=1,
        resource_class="standard",
        version="0.3.0",
        created_at=NOW,
        owner_kind=RunnerOwnerKind.user,
        owner_id=str(owner),
    )
    await runners.add(runner)
    service = RunnerJobService(
        queue,
        JobQueueService(queue, clock=lambda: NOW),
        runners,
        JobTokenSigner([b"k" * 32]),
        JobWakeup(),
        lease_s=45.0,
        timeout_grace_s=15.0,
        clock=lambda: NOW,
        personal_settings=settings,
        users=users,
    )
    if users is not None:
        await users.add(
            User(str(owner), "anna@example.org", "anna@example.org", "Анна", UserStatus.active, created_at=NOW)
        )
    spec = replace(make_compile_spec(), id=uuid4())
    project = spec.project_id
    queue.set_project(ProjectRouteInfo(project, str(owner), None, ProjectBuildRunners.shared))
    envelope = JobEnvelope(spec=spec, manifest=(), timeout_s=300.0, attempt=1, job_token="-")
    payload = {k: v for k, v in encode_envelope(envelope).items() if k not in {"job_token", "attempt"}}
    await queue.enqueue(
        EnqueueRequest(
            job_id=spec.id,
            kind=spec.kind,
            project_id=project,
            user_id=owner,
            tags=spec.tags,
            payload=payload,
            timeout_s=300.0,
            timeout_personal_s=900.0,
            route=JobRoute.personal_first,
            route_owner_id=str(owner),
            personal_until=NOW + timedelta(seconds=5),
        )
    )
    return service, queue, runner, settings, owner


async def test__poll__personal_runner__gets_owner_job_with_trimmed_actor_and_own_timeout() -> None:
    service, _, runner, _, _ = await _world()

    response = await service.poll(runner, PollRequest(wait_s=0))

    assert response.envelope is not None
    actor = response.envelope.spec.actor
    assert (actor.email, actor.link_id, actor.is_instance_admin) == (None, None, False)
    assert actor.id == "u1"
    assert response.envelope.timeout_s == 900.0


async def test__poll__personal_runners_disabled__no_work() -> None:
    service, queue, runner, settings, _ = await _world()
    settings.value = PersonalRunnerSettings(enabled=False)

    response = await service.poll(runner, PollRequest(wait_s=0))

    assert response.envelope is None
    assert all(job.runner_scope is None for job in await queue.list())


async def test__poll__no_free_build_slot__takes_no_build() -> None:
    service, _, runner, _, _ = await _world()

    response = await service.poll(runner, PollRequest(wait_s=0, free_slots=0, free_ai_slots=1))

    assert response.envelope is None


async def test__poll__scope_comes_from_the_record_not_the_runner() -> None:
    service, queue, runner, _, _ = await _world()
    await service.poll(runner, PollRequest(wait_s=0))
    (job,) = await queue.list()
    assert job.runner_scope is RunnerScope.personal


async def test__poll__token_rotated_after_authentication__old_poll_gets_nothing() -> None:
    """Хозяин сменил утёкший токен, пока на старом шёл долгий опрос: задача ему не достаётся."""
    runners = InMemoryRunnerRepository()
    service, queue, runner, _, _ = await _world(runners=runners)
    await runners.set_token_hash(runner.id, "rotated")

    response = await service.poll(runner, PollRequest(wait_s=0))

    assert response.envelope is None
    assert all(job.runner_id is None for job in await queue.list())


async def test__poll__owner_disabled_after_authentication__no_work() -> None:
    users = InMemoryUserRepository()
    service, queue, runner, _, owner = await _world(users=users)
    user = await users.get(str(owner))
    assert user is not None
    await users.update(replace(user, status=UserStatus.disabled))

    response = await service.poll(runner, PollRequest(wait_s=0))

    assert response.envelope is None
    assert all(job.runner_id is None for job in await queue.list())


async def test__poll__active_owner__still_gets_work() -> None:
    service, _, runner, _, _ = await _world(users=InMemoryUserRepository())

    response = await service.poll(runner, PollRequest(wait_s=0))

    assert response.envelope is not None
