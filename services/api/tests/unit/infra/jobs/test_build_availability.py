"""Доступность сборки: теги живых общих раннеров и личные раннеры владельца по решению маршрута."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.availability import BuildAvailability
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.routing import JobRoute, RouteDecision, RouteReason
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.infra.jobs.availability import LocalBuildAvailability, RunnerBuildAvailability

from tests.fakes.runners import InMemoryRunnerRepository

_NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
_USER = uuid4()
_PROJECT = uuid4()
_ACTOR = Actor.user(str(_USER), "Иван")


def _runner(*tags: str, seen: datetime | None = _NOW, paused: bool = False) -> Runner:
    return Runner(
        id=uuid4().hex,
        name="r",
        token_hash="h",
        tags=frozenset(tags),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=_NOW,
        last_seen_at=seen,
        paused=paused,
    )


class _PersonalRouter:
    """Личный раннер владельца берёт только перечисленные теги."""

    def __init__(self, tags: frozenset[str], reason: RouteReason = RouteReason.waiting_personal) -> None:
        self.tags = tags
        self.reason = reason
        self.asked: list[frozenset[str]] = []

    async def decide(self, *, kind: JobKind, tags: frozenset[str], project_id: UUID, user_id: UUID) -> RouteDecision:
        self.asked.append(tags)
        if not tags <= self.tags:
            return RouteDecision.shared(RouteReason.fallback_offline)
        if self.reason is RouteReason.fallback_busy:
            return RouteDecision.shared(RouteReason.fallback_busy)
        return RouteDecision(
            route=JobRoute.personal_first,
            reason=self.reason,
            route_owner_id=_USER.hex,
            personal_until=_NOW + timedelta(seconds=30),
        )


async def _availability(*runners: Runner, router: _PersonalRouter | None = None) -> BuildAvailability:
    repo = InMemoryRunnerRepository()
    for runner in runners:
        await repo.add(runner)
    return await RunnerBuildAvailability(repo, router=router, clock=lambda: _NOW).of(_PROJECT, _ACTOR)


async def test__of__no_runners__nothing_served() -> None:
    result = await _availability()

    assert result == BuildAvailability(cloud=True, any_runner=False, tags=frozenset())
    assert not result.serves({"tex"})
    assert result.serves(set())


async def test__of__live_shared_runner__its_build_tags() -> None:
    result = await _availability(_runner("tex", "pack"))

    assert result.any_runner
    assert result.tags == frozenset({"tex"})
    assert not result.serves({"office"})


@pytest.mark.parametrize(
    "runner",
    [
        _runner("tex", seen=_NOW - timedelta(minutes=10)),
        _runner("tex", seen=None),
        _runner("tex", paused=True),
    ],
    ids=["stale", "never_seen", "paused"],
)
async def test__of__dead_runner__not_counted(runner: Runner) -> None:
    result = await _availability(runner)

    assert not result.any_runner
    assert result.tags == frozenset()


async def test__of__personal_runner_of_owner__adds_its_tags() -> None:
    router = _PersonalRouter(frozenset({"office"}), RouteReason.waiting_personal)

    result = await _availability(_runner("tex"), router=router)

    assert result.tags == frozenset({"tex", "office"})
    assert router.asked == [frozenset({"office"})]


async def test__of__all_tags_shared__router_not_asked() -> None:
    router = _PersonalRouter(frozenset())

    await _availability(_runner("tex", "office"), router=router)

    assert router.asked == []


async def test__local__everything_served() -> None:
    result = await LocalBuildAvailability().of(_PROJECT, Actor.local())

    assert not result.cloud
    assert result.serves({"tex", "office"})


async def _general(*runners: Runner) -> BuildAvailability:
    repo = InMemoryRunnerRepository()
    for runner in runners:
        await repo.add(runner)
    return await RunnerBuildAvailability(repo, router=_PersonalRouter(frozenset({"tex"})), clock=lambda: _NOW).general()


@pytest.mark.parametrize(
    ("runners", "any_runner", "tags"),
    [
        ((), False, frozenset()),
        ((_runner("tex", "pack"),), True, frozenset({"tex"})),
        ((_runner("tex", paused=True),), False, frozenset()),
    ],
    ids=["none", "live_shared", "paused"],
)
async def test__general__only_live_shared_runners_count(
    runners: tuple[Runner, ...], any_runner: bool, tags: frozenset[str]
) -> None:
    result = await _general(*runners)

    assert result == BuildAvailability(cloud=True, any_runner=any_runner, tags=tags)


async def test__local__general__everything_served() -> None:
    result = await LocalBuildAvailability().general()

    assert not result.cloud
    assert result.serves({"tex"})
