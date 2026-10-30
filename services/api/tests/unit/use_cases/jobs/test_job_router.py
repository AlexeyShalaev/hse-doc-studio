"""Маршрут при постановке: все строки таблицы «кто где собирает» и шаги решения по порядку."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.queue import EnqueueRequest
from hse_doc_studio.core.jobs.routing import (
    JobRoute,
    PersonalRunnerSettings,
    ProjectBuildRunners,
    ProjectRouteInfo,
    RouteReason,
)
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.use_cases.jobs.routing import JobRouter

from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRunnerRepository

NOW = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)
TEX = frozenset({"tex"})


class _Settings:
    def __init__(self, value: PersonalRunnerSettings) -> None:
        self.value = value

    async def current(self) -> PersonalRunnerSettings:
        return self.value


class _Projects:
    def __init__(self) -> None:
        self.items: dict[UUID, ProjectRouteInfo] = {}

    async def get(self, project_id: UUID) -> ProjectRouteInfo | None:
        return self.items.get(project_id)

    async def set_build_runners(self, project_id: UUID, policy: ProjectBuildRunners) -> bool:
        return False


class _World:
    def __init__(self) -> None:
        self.owner = uuid4()
        self.settings = _Settings(PersonalRunnerSettings())
        self.projects = _Projects()
        self.runners = InMemoryRunnerRepository()
        self.queue = InMemoryJobQueue(clock=lambda: NOW)
        self.router = JobRouter(self.settings, self.projects, self.runners, self.queue, clock=lambda: NOW)
        self.project = uuid4()
        self.projects.items[self.project] = ProjectRouteInfo(
            project_id=self.project,
            owner_user_id=str(self.owner),
            owner_org_id=None,
            build_runners=ProjectBuildRunners.shared,
        )

    async def runner(self, **changes: object) -> Runner:
        runner = Runner(
            id=uuid4().hex,
            name="MacBook",
            token_hash=uuid4().hex,
            tags=frozenset({"tex", "pack"}),
            concurrency=1,
            resource_class="standard",
            version="0.3.0",
            created_at=NOW,
            last_seen_at=NOW - timedelta(seconds=5),
            owner_kind=RunnerOwnerKind.user,
            owner_id=str(self.owner),
        )
        runner = replace(runner, **changes)  # type: ignore[arg-type]
        await self.runners.add(runner)
        return runner

    def policy(self, policy: ProjectBuildRunners) -> None:
        self.projects.items[self.project] = replace(self.projects.items[self.project], build_runners=policy)

    async def decide(self, *, user: UUID | None = None, kind: JobKind = JobKind.compile, tags: frozenset[str] = TEX):
        return await self.router.decide(kind=kind, tags=tags, project_id=self.project, user_id=user or self.owner)


@pytest.fixture
def world() -> _World:
    return _World()


async def test__decide__owner_with_online_runner__waits_for_it(world: _World) -> None:
    await world.runner()
    decision = await world.decide()
    assert decision.route is JobRoute.personal_first
    assert (decision.reason, decision.route_owner_id, decision.personal_until) == (
        RouteReason.waiting_personal,
        str(world.owner),
        NOW + timedelta(seconds=5),
    )


async def test__decide__disabled_installation_wide__shared(world: _World) -> None:
    await world.runner()
    world.settings.value = PersonalRunnerSettings(enabled=False)
    assert (await world.decide()).reason is RouteReason.disabled


async def test__decide__signature_check__never_personal(world: _World) -> None:
    await world.runner(tags=frozenset({"verify"}))
    decision = await world.decide(kind=JobKind.verify_detached, tags=frozenset({"verify"}))
    assert (decision.route, decision.reason) == (JobRoute.shared, RouteReason.kind_not_allowed)


async def test__decide__org_project__shared(world: _World) -> None:
    await world.runner()
    world.projects.items[world.project] = replace(world.projects.items[world.project], owner_user_id=None)
    assert (await world.decide()).reason is RouteReason.org_project


async def test__decide__coauthor__follows_policy(world: _World) -> None:
    await world.runner()
    coauthor = uuid4()
    assert (await world.decide(user=coauthor)).reason is RouteReason.policy_shared
    world.policy(ProjectBuildRunners.owner)
    decision = await world.decide(user=coauthor)
    assert (decision.route, decision.route_owner_id) == (JobRoute.personal_first, str(world.owner))


async def test__decide__coauthor_runner_never_builds_someone_elses_project(world: _World) -> None:
    coauthor = uuid4()
    await world.runner(owner_id=str(coauthor))
    world.policy(ProjectBuildRunners.owner)
    assert (await world.decide(user=coauthor)).reason is RouteReason.fallback_offline


@pytest.mark.parametrize(
    "changes",
    [
        {"paused": True},
        {"revoked_at": NOW},
        {"last_seen_at": NOW - timedelta(minutes=3)},
        {"last_seen_at": None},
        {"offline_at": NOW},
        {"tags": frozenset({"pack"})},
    ],
    ids=["paused", "revoked", "stale", "never_seen", "said_offline", "no_tag"],
)
async def test__decide__no_matching_runner_online__fallback_offline(world: _World, changes: dict[str, object]) -> None:
    await world.runner(**changes)
    assert (await world.decide()).reason is RouteReason.fallback_offline


async def test__decide__capacity_used_by_waiting_and_running__fallback_busy(world: _World) -> None:
    await world.runner(concurrency=1)
    first = await world.decide()
    assert first.route is JobRoute.personal_first
    await world.queue.enqueue(
        EnqueueRequest(
            job_id=uuid4(),
            kind=JobKind.compile,
            project_id=world.project,
            user_id=world.owner,
            tags=TEX,
            payload={},
            route=first.route,
            route_owner_id=first.route_owner_id,
            personal_until=first.personal_until,
        )
    )
    assert (await world.decide()).reason is RouteReason.fallback_busy


@pytest.mark.parametrize("wait_s", [0, 60])
async def test__decide__window_follows_settings(world: _World, wait_s: int) -> None:
    await world.runner()
    world.settings.value = PersonalRunnerSettings(wait_s=wait_s)
    assert (await world.decide()).personal_until == NOW + timedelta(seconds=wait_s)
