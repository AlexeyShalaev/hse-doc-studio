"""Задача, которую не может взять ни один раннер: ждёт с причиной или по таймеру заканчивается `failed`."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import EnqueueRequest, QueuedJob
from hse_doc_studio.core.jobs.routing import JobRoute, PersonalRunnerSettings, RouteReason
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.use_cases.jobs.stranded import QueuedJobFit, StrandedJobSweeper

from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRunnerRepository

START = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)
OFFICE = frozenset({"office"})


class _Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def tick(self, **delta: float) -> None:
        self.now += timedelta(**delta)


class _Settings:
    def __init__(self) -> None:
        self.value = PersonalRunnerSettings()

    async def current(self) -> PersonalRunnerSettings:
        return self.value


class _Router:
    """Личные раннеры владельца проекта разрешены задаче, если владелец задан."""

    def __init__(self, owner: str | None) -> None:
        self.owner = owner
        self.asked = 0

    async def personal_owner(self, *, kind: JobKind, project_id: UUID, user_id: UUID) -> str | None:
        self.asked += 1
        return self.owner


class _World:
    def __init__(self) -> None:
        self.clock = _Clock()
        self.owner = uuid4()
        self.queue = InMemoryJobQueue(clock=self.clock)
        self.runners = InMemoryRunnerRepository()
        self.settings = _Settings()
        self.router = _Router(self.owner.hex)
        self.fit = QueuedJobFit(self.router, self.settings)
        self.sweeper = StrandedJobSweeper(self.queue, self.runners, self.fit, clock=self.clock)

    async def runner(self, *tags: str, personal: bool = False, **changes: object) -> Runner:
        runner = Runner(
            id=uuid4().hex,
            name="r",
            token_hash=uuid4().hex,
            tags=frozenset(tags),
            concurrency=1,
            resource_class="standard",
            version="0.3.0",
            created_at=START,
            last_seen_at=START,
            owner_kind=RunnerOwnerKind.user if personal else RunnerOwnerKind.instance,
            owner_id=self.owner.hex if personal else None,
        )
        runner = replace(runner, **changes)  # type: ignore[arg-type]
        await self.runners.add(runner)
        return runner

    async def put(self, tags: frozenset[str] = OFFICE, *, personal: bool = True, **changes: object) -> QueuedJob:
        extra: dict[str, object] = {}
        if personal:
            extra = {
                "route": JobRoute.personal_first,
                "route_owner_id": self.owner.hex,
                "personal_until": self.clock.now + timedelta(seconds=5),
                "route_reason": RouteReason.waiting_personal,
            }
        extra.update(changes)
        extra.setdefault("kind", JobKind.compile)
        extra.setdefault("project_id", uuid4())
        request = EnqueueRequest(
            job_id=uuid4(),
            user_id=self.owner,
            tags=tags,
            payload={},
            **extra,  # type: ignore[arg-type]
        )
        return (await self.queue.enqueue(request)).job

    async def state(self, job: QueuedJob) -> tuple[JobState, str | None]:
        current = await self.queue.get(job.id)
        assert current is not None
        return current.state, current.error_code


@pytest.fixture
def world() -> _World:
    return _World()


async def test__sweep__personal_runner_online_but_busy__keeps_waiting(world: _World) -> None:
    # Все подходящие раннеры заняты: это очередь, а не отказ, сколько бы ни ждали.
    await world.runner("tex", "office", personal=True)
    job = await world.put()

    world.clock.tick(hours=2)
    await world.runner("tex", "office", personal=True, last_seen_at=world.clock.now)
    assert await world.sweeper.sweep() == ()

    assert await world.state(job) == (JobState.queued, None)


async def test__sweep__personal_runner_paused_after_enqueue__waits_then_runner_paused(world: _World) -> None:
    # Прод: сборка pptx ждала личный раннер с office (waiting_personal), а его поставили на паузу.
    await world.runner("tex")
    await world.runner("tex", "office", personal=True, paused=True)
    job = await world.put()

    assert await world.sweeper.sweep() == ()
    world.clock.tick(minutes=29)
    assert await world.sweeper.sweep() == ()
    assert await world.state(job) == (JobState.queued, None)

    world.clock.tick(minutes=2)
    (failed,) = await world.sweeper.sweep()

    assert failed.id == job.id
    assert await world.state(job) == (JobState.failed, "runner_paused")


async def test__sweep__pause_lifted_in_time__job_survives(world: _World) -> None:
    paused = await world.runner("office", personal=True, paused=True)
    job = await world.put()
    await world.sweeper.sweep()

    world.clock.tick(minutes=20)
    await world.runners.set_paused(paused.id, False)
    await world.runners.touch(paused.id, world.clock.now)
    await world.sweeper.sweep()
    world.clock.tick(minutes=20)
    await world.runners.touch(paused.id, world.clock.now)

    assert await world.sweeper.sweep() == ()
    assert await world.state(job) == (JobState.queued, None)


async def test__sweep__runner_offline__runner_offline_after_five_minutes(world: _World) -> None:
    await world.runner("office", personal=True, last_seen_at=START - timedelta(minutes=10))
    job = await world.put()
    await world.sweeper.sweep()

    world.clock.tick(minutes=4)
    assert await world.sweeper.sweep() == ()
    world.clock.tick(minutes=2)
    await world.sweeper.sweep()

    assert await world.state(job) == (JobState.failed, "runner_offline")


async def test__sweep__runner_revoked__no_runner_for_tags_after_a_minute(world: _World) -> None:
    await world.runner("tex")
    await world.runner("office", personal=True, revoked_at=START)
    job = await world.put()
    await world.sweeper.sweep()

    world.clock.tick(seconds=61)
    await world.sweeper.sweep()

    assert await world.state(job) == (JobState.failed, "no_runner_for_tags")


async def test__sweep__shared_route__personal_runner_not_counted(world: _World) -> None:
    # Сборка на общем маршруте (не fallback_busy) личный раннер не возьмёт, даже если он в сети.
    await world.runner("office", personal=True)
    job = await world.put(personal=False, route_reason=RouteReason.fallback_offline)
    await world.sweeper.sweep()

    world.clock.tick(minutes=2)
    await world.sweeper.sweep()

    assert await world.state(job) == (JobState.failed, "no_runner_for_tags")


async def test__sweep__fallback_busy__owner_personal_runner_counted(world: _World) -> None:
    await world.runner("office", personal=True)
    job = await world.put(personal=False, route_reason=RouteReason.fallback_busy)

    world.clock.tick(minutes=2)
    await world.runner("office", personal=True, last_seen_at=world.clock.now)
    assert await world.sweeper.sweep() == ()

    assert await world.state(job) == (JobState.queued, None)


async def test__sweep__personal_disabled__only_shared_counted(world: _World) -> None:
    await world.runner("office", personal=True)
    job = await world.put()
    world.settings.value = PersonalRunnerSettings(enabled=False)
    await world.sweeper.sweep()

    world.clock.tick(minutes=2)
    await world.sweeper.sweep()

    assert await world.state(job) == (JobState.failed, "no_runner_for_tags")


async def test__sweep__relay_job__untouched(world: _World) -> None:
    pinned = await world.put(
        frozenset({"ai"}),
        personal=False,
        kind=JobKind.ai_relay,
        route=JobRoute.pinned,
        target_runner_id=uuid4(),
    )

    world.clock.tick(hours=1)
    await world.sweeper.sweep()
    world.clock.tick(hours=1)

    assert await world.sweeper.sweep() == ()
    assert await world.state(pinned) == (JobState.queued, None)


async def test__sweep__long_queue_of_one_project__route_asked_once(world: _World) -> None:
    await world.runner("office", personal=True)
    project = uuid4()
    for _ in range(5):
        await world.put(personal=False, route_reason=RouteReason.fallback_busy, project_id=project)

    await world.sweeper.sweep()

    assert world.router.asked == 1
