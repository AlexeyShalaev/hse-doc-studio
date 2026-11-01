"""Причина ожидания сборки по записи очереди и поток событий сборки с причиной ожидания."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from hse_doc_studio.api import compile_stream
from hse_doc_studio.core.compile.wait import (
    CompilePlacementInfo,
    CompileWaitInfo,
    CompileWaitReason,
    NoCompileWait,
    PlacementFallback,
    PlacementOwner,
    PlacementState,
)
from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass
from hse_doc_studio.core.jobs.queue import EnqueueRequest, RunnerRef
from hse_doc_studio.core.jobs.routing import JobRoute, ProjectBuildRunners, ProjectRouteInfo, RouteReason, RunnerScope
from hse_doc_studio.core.jobs.runners import Runner, RunnerOwnerKind
from hse_doc_studio.infra.jobs.compile_wait import QueueCompileWaitReader

from tests.fakes.job_queue import InMemoryJobQueue
from tests.fakes.runners import InMemoryRunnerRepository

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def _request(job_id: UUID | None = None, user_id: UUID | None = None, **kwargs: object) -> EnqueueRequest:
    return EnqueueRequest(
        job_id=job_id or uuid4(),
        kind=JobKind.compile,
        project_id=kwargs.pop("project_id", uuid4()),  # type: ignore[arg-type]
        user_id=user_id or uuid4(),
        tags=frozenset({"tex"}),
        payload={},
        **kwargs,  # type: ignore[arg-type]
    )


async def _runner(runners: InMemoryRunnerRepository, *, seen: datetime | None, tags: set[str]) -> None:
    await runners.add(
        Runner(
            id=uuid4().hex,
            name="r",
            token_hash="h",
            tags=frozenset(tags),
            concurrency=1,
            resource_class="standard",
            version="1",
            created_at=NOW - timedelta(days=1),
            last_seen_at=seen,
        )
    )


def _reader(queue: InMemoryJobQueue, runners: InMemoryRunnerRepository) -> QueueCompileWaitReader:
    return QueueCompileWaitReader(queue, runners, clock=lambda: NOW)


async def test__no_job__no_wait() -> None:
    assert await _reader(InMemoryJobQueue(), InMemoryRunnerRepository()).of(uuid4()) is None


async def test__queued_with_online_runner__position_counts_jobs_ahead() -> None:
    queue, runners = InMemoryJobQueue(), InMemoryRunnerRepository()
    await _runner(runners, seen=NOW, tags={"tex", "office"})
    first, second = uuid4(), uuid4()
    await queue.enqueue(_request(first))
    await queue.enqueue(_request(second))

    info = await _reader(queue, runners).of(second)

    assert info == CompileWaitInfo(CompileWaitReason.queued, queue_position=2)


async def test__queued_newcomer_after_a_flood__position_follows_fair_share_not_arrival() -> None:
    queue, runners = InMemoryJobQueue(), InMemoryRunnerRepository()
    await _runner(runners, seen=NOW, tags={"tex"})
    flooder, newcomer = uuid4(), uuid4()
    for _ in range(5):
        await queue.enqueue(_request(user_id=flooder))
    job_id = uuid4()
    await queue.enqueue(_request(job_id, user_id=newcomer))

    info = await _reader(queue, runners).of(job_id)

    assert info is not None
    assert info.queue_position <= 2


async def test__queued_without_a_suitable_runner__no_runner() -> None:
    queue, runners = InMemoryJobQueue(), InMemoryRunnerRepository()
    await _runner(runners, seen=NOW, tags={"office"})
    await _runner(runners, seen=NOW - timedelta(hours=1), tags={"tex"})
    job_id = uuid4()
    await queue.enqueue(_request(job_id))

    info = await _reader(queue, runners).of(job_id)

    assert info is not None
    assert info.reason is CompileWaitReason.no_runner


async def test__interactive_job_is_ahead_of_checks_in_the_position() -> None:
    queue, runners = InMemoryJobQueue(), InMemoryRunnerRepository()
    await _runner(runners, seen=NOW, tags={"tex"})
    await queue.enqueue(_request(priority_class=JobPriorityClass.checks))
    interactive = uuid4()
    await queue.enqueue(_request(interactive, priority_class=JobPriorityClass.interactive))

    info = await _reader(queue, runners).of(interactive)

    assert info is not None
    assert info.queue_position == 1


async def test__requeued_after_lost_runner__runner_lost_with_attempts() -> None:
    queue, runners = InMemoryJobQueue(clock=lambda: NOW), InMemoryRunnerRepository()
    await _runner(runners, seen=NOW, tags={"tex"})
    job_id = uuid4()
    await queue.enqueue(_request(job_id, max_attempts=3))
    claimed = await queue.claim(RunnerRef(uuid4(), frozenset({"tex"})), lease_s=-1.0)
    assert claimed is not None
    await queue.requeue_expired()

    info = await _reader(queue, runners).of(job_id)

    assert info is not None
    assert (info.reason, info.attempt, info.max_attempts) == (CompileWaitReason.runner_lost, 2, 3)


async def test__superseded_job__superseded_even_though_it_is_finished() -> None:
    queue, runners = InMemoryJobQueue(), InMemoryRunnerRepository()
    old = uuid4()
    await queue.enqueue(_request(old, coalesce_key="doc"))
    await queue.enqueue(_request(coalesce_key="doc"))

    info = await _reader(queue, runners).of(old)

    assert info == CompileWaitInfo(CompileWaitReason.superseded)


async def test__running_job__no_wait() -> None:
    queue, runners = InMemoryJobQueue(clock=lambda: NOW), InMemoryRunnerRepository()
    job_id = uuid4()
    await queue.enqueue(_request(job_id))
    await queue.claim(RunnerRef(uuid4(), frozenset({"tex"})), lease_s=45.0)

    assert await _reader(queue, runners).of(job_id) is None


class _ScriptedWaits:
    enabled = True

    def __init__(
        self, script: list[CompileWaitInfo | None], placements: list[CompilePlacementInfo | None] | None = None
    ) -> None:
        self._script = script
        self._placements = placements or [None]
        self.viewers: list[str | None] = []

    async def of(self, compile_id: UUID) -> CompileWaitInfo | None:  # noqa: ARG002
        return self._script.pop(0) if len(self._script) > 1 else self._script[0]

    async def placement_of(self, compile_id: UUID, viewer_id: str | None) -> CompilePlacementInfo | None:  # noqa: ARG002
        self.viewers.append(viewer_id)
        return self._placements.pop(0) if len(self._placements) > 1 else self._placements[0]


async def _lines(*lines: str, delay: float = 0.0) -> AsyncIterator[str]:
    await asyncio.sleep(delay)
    for line in lines:
        yield line


async def test__merged_events__wait_changes_are_emitted_once_and_cleared(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(compile_stream, "_WAIT_POLL_S", 0.01)
    waits = _ScriptedWaits(
        [
            CompileWaitInfo(CompileWaitReason.queued, 1),
            CompileWaitInfo(CompileWaitReason.queued, 1),
            None,
        ]
    )

    events = [e async for e in compile_stream.merged_events(_lines("a", "b", delay=0.1), waits, uuid4())]  # type: ignore[arg-type]

    kinds = [kind for kind, _ in events]
    assert kinds.count("wait") == 2
    waits_only = [value for kind, value in events if kind == "wait"]
    assert '"reason":"queued"' in waits_only[0]
    assert waits_only[1] == "null"
    assert [v for k, v in events if k == "log"] == ["a", "b"]


async def test__merged_events__placement_changes_are_emitted_for_the_viewer(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(compile_stream, "_WAIT_POLL_S", 0.01)
    waiting = CompilePlacementInfo(PlacementState.waiting_personal, "MacBook", PlacementOwner.me, wait_s=5)
    taken = CompilePlacementInfo(PlacementState.personal, "MacBook", PlacementOwner.me)
    waits = _ScriptedWaits([None], [waiting, waiting, taken])

    events = [
        e
        async for e in compile_stream.merged_events(_lines("a", delay=0.1), waits, uuid4(), "anna")  # type: ignore[arg-type]
    ]

    placements = [value for kind, value in events if kind == "placement"]
    assert len(placements) == 2
    assert '"state":"waiting_personal"' in placements[0]
    assert '"state":"personal"' in placements[1]
    assert set(waits.viewers) == {"anna"}


async def test__merged_events__without_a_queue_only_logs() -> None:
    events = [e async for e in compile_stream.merged_events(_lines("x"), NoCompileWait(), uuid4())]

    assert events == [("log", "x")]


async def test__personal_first_in_window__waits_for_personal_runner() -> None:
    queue, runners = InMemoryJobQueue(clock=lambda: NOW), InMemoryRunnerRepository()
    job = uuid4()
    await queue.enqueue(
        _request(job, route=JobRoute.personal_first, route_owner_id="u1", personal_until=NOW + timedelta(seconds=4.2))
    )

    info = await _reader(queue, runners).of(job)

    assert info == CompileWaitInfo(CompileWaitReason.personal_runner, None, 5)


async def test__after_window_only_shared_runners_count() -> None:
    queue, runners = InMemoryJobQueue(clock=lambda: NOW), InMemoryRunnerRepository()
    await runners.add(
        Runner(
            id=uuid4().hex,
            name="mine",
            token_hash="h",
            tags=frozenset({"tex"}),
            concurrency=1,
            resource_class="standard",
            version="1",
            created_at=NOW,
            last_seen_at=NOW,
            owner_kind=RunnerOwnerKind.user,
            owner_id="u1",
        )
    )
    job = uuid4()
    await queue.enqueue(_request(job, route=JobRoute.personal_first, route_owner_id="u1", personal_until=NOW))

    info = await _reader(queue, runners).of(job)

    assert info is not None
    assert info.reason is CompileWaitReason.no_runner


class _Projects:
    def __init__(self, info: ProjectRouteInfo) -> None:
        self.info = info

    async def get(self, project_id: UUID) -> ProjectRouteInfo | None:
        return self.info if project_id == self.info.project_id else None

    async def set_build_runners(self, project_id: UUID, policy: ProjectBuildRunners) -> bool:
        return False


async def _placement_world(policy: ProjectBuildRunners = ProjectBuildRunners.shared):
    queue, runners = InMemoryJobQueue(clock=lambda: NOW), InMemoryRunnerRepository()
    runner = Runner(
        id=uuid4().hex,
        name="MacBook",
        token_hash="h",
        tags=frozenset({"tex"}),
        concurrency=1,
        resource_class="standard",
        version="1",
        created_at=NOW,
        last_seen_at=NOW,
        owner_kind=RunnerOwnerKind.user,
        owner_id="anna",
    )
    await runners.add(runner)
    project = uuid4()
    reader = QueueCompileWaitReader(
        queue, runners, clock=lambda: NOW, projects=_Projects(ProjectRouteInfo(project, "anna", None, policy))
    )
    return queue, runner, project, reader


async def test__placement__waiting_then_personal_names_the_runner_for_owner_and_coauthor() -> None:
    queue, runner, project, reader = await _placement_world(ProjectBuildRunners.owner)
    job = uuid4()
    await queue.enqueue(
        _request(
            job,
            project_id=project,
            route=JobRoute.personal_first,
            route_owner_id="anna",
            personal_until=NOW + timedelta(seconds=5),
        )
    )
    waiting = await reader.placement_of(job, "anna")
    assert waiting == CompilePlacementInfo(PlacementState.waiting_personal, "MacBook", PlacementOwner.me, wait_s=5)
    queue.set_project(ProjectRouteInfo(project, "anna", None, ProjectBuildRunners.owner))
    await queue.claim(
        RunnerRef(id=UUID(runner.id), tags=runner.tags, scope=RunnerScope.personal, owner_id="anna"), lease_s=45
    )
    assert await reader.placement_of(job, "boris") == CompilePlacementInfo(
        PlacementState.personal, "MacBook", PlacementOwner.owner
    )


async def test__placement__fallback_only_for_viewers_who_could_go_personal() -> None:
    queue, _, project, reader = await _placement_world()
    job = uuid4()
    await queue.enqueue(_request(job, project_id=project, route_reason=RouteReason.fallback_offline))
    assert await reader.placement_of(job, "anna") == CompilePlacementInfo(
        PlacementState.shared, fallback=PlacementFallback.offline
    )
    assert await reader.placement_of(job, "boris") == CompilePlacementInfo(PlacementState.shared)


async def test__placement__timeout_fallback_carries_the_window() -> None:
    queue, _, project, reader = await _placement_world()
    job = uuid4()
    await queue.enqueue(
        _request(job, project_id=project, route=JobRoute.personal_first, route_owner_id="anna", personal_until=NOW)
    )
    await queue.claim(RunnerRef(id=uuid4(), tags=frozenset({"tex"})), lease_s=45)
    assert await reader.placement_of(job, "anna") == CompilePlacementInfo(
        PlacementState.shared, fallback=PlacementFallback.timeout, wait_s=5
    )


async def test__placement__disabled_note_only_for_runner_owner() -> None:
    # Даже при политике `owner` соавтор не видит «администратор выключил личные раннеры»: это не его раннеры.
    queue, _, project, reader = await _placement_world(ProjectBuildRunners.owner)
    job = uuid4()
    await queue.enqueue(_request(job, project_id=project, route_reason=RouteReason.disabled))
    assert await reader.placement_of(job, "anna") == CompilePlacementInfo(
        PlacementState.shared, fallback=PlacementFallback.disabled
    )
    assert await reader.placement_of(job, "boris") == CompilePlacementInfo(PlacementState.shared)
