"""Причина ожидания сборки по записи очереди: место в очереди, нет раннера, потерянный раннер, замена."""

from __future__ import annotations

import math
from uuid import UUID

from hse_doc_studio.core.compile.wait import (
    CompilePlacementInfo,
    CompileWaitInfo,
    CompileWaitReason,
    PlacementFallback,
    PlacementOwner,
    PlacementState,
)
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.enums import JobState, RunnerErrorCode
from hse_doc_studio.core.jobs.queue import IJobQueue, QueuedJob
from hse_doc_studio.core.jobs.routing import (
    IPersonalRunnerSettings,
    IProjectRoutePolicy,
    JobRoute,
    PersonalRunnerSettings,
    ProjectBuildRunners,
    RouteReason,
    RunnerScope,
)
from hse_doc_studio.core.jobs.runners import IRunnerRepository


class QueueCompileWaitReader:
    enabled = True

    def __init__(
        self,
        queue: IJobQueue,
        runners: IRunnerRepository,
        *,
        clock: Clock = utc_now,
        projects: IProjectRoutePolicy | None = None,
        personal: IPersonalRunnerSettings | None = None,
    ) -> None:
        self._queue = queue
        self._runners = runners
        self._clock = clock
        self._projects = projects
        self._personal = personal

    async def placement_of(self, compile_id: UUID, viewer_id: str | None) -> CompilePlacementInfo | None:
        """Где идёт сборка для этого зрителя (таблица 9.4 спецификации личных раннеров)."""
        job = await self._queue.get(compile_id)
        if job is None:
            return None
        settings = await self._personal.current() if self._personal is not None else PersonalRunnerSettings()
        now = self._clock()
        if (
            job.state is JobState.queued
            and job.route is JobRoute.personal_first
            and job.personal_until is not None
            and job.personal_until > now
            and job.route_owner_id is not None
        ):
            online = [
                r
                for r in await self._runners.list_owned(job.route_owner_id)
                if runner_status(r, now) is RunnerStatus.online and job.tags <= r.tags
            ]
            return CompilePlacementInfo(
                PlacementState.waiting_personal,
                runner_name=online[0].name if online else None,
                runner_owner=_owner_of(job.route_owner_id, viewer_id),
                wait_s=settings.wait_s,
            )
        if job.runner_scope is RunnerScope.personal and job.runner_id is not None:
            runner = await self._runners.get(job.runner_id.hex)
            return CompilePlacementInfo(
                PlacementState.personal,
                runner_name=runner.name if runner is not None else None,
                runner_owner=_owner_of(runner.owner_id if runner is not None else None, viewer_id),
            )
        fallback = _FALLBACKS.get(job.route_reason) if job.route_reason is not None else None
        if fallback is not None and not await self._fallback_visible(job, viewer_id):
            fallback = None
        return CompilePlacementInfo(
            PlacementState.shared,
            fallback=fallback,
            wait_s=settings.wait_s if fallback is PlacementFallback.timeout else None,
        )

    async def _fallback_visible(self, job: QueuedJob, viewer_id: str | None) -> bool:
        """Пометку видит тот, чья сборка вообще могла пойти на личный раннер, и только если раннеры у владельца есть."""
        if self._projects is None or viewer_id is None:
            return False
        project = await self._projects.get(job.project_id)
        if project is None or project.owner_user_id is None:
            return False
        if job.route_reason is RouteReason.disabled and viewer_id != project.owner_user_id:
            # «Администратор выключил личные раннеры» касается только их владельца (спецификация 4.7).
            return False
        if viewer_id != project.owner_user_id and project.build_runners is not ProjectBuildRunners.owner:
            return False
        return any(r.revoked_at is None for r in await self._runners.list_owned(project.owner_user_id))

    async def of(self, compile_id: UUID) -> CompileWaitInfo | None:
        job = await self._queue.get(compile_id)
        if job is None:
            return None
        if job.state is JobState.cancelled and job.error_code == RunnerErrorCode.superseded.value:
            return CompileWaitInfo(CompileWaitReason.superseded)
        if job.state is not JobState.queued:
            return None
        if job.attempt > 0:
            # Раннер пропал посреди сборки: задача вернулась в очередь на повтор.
            return CompileWaitInfo(
                CompileWaitReason.runner_lost, await self._position(job), None, job.attempt + 1, job.max_attempts
            )
        now = self._clock()
        if job.route is JobRoute.personal_first and job.personal_until is not None and job.personal_until > now:
            left = math.ceil((job.personal_until - now).total_seconds())
            return CompileWaitInfo(CompileWaitReason.personal_runner, None, max(left, 0))
        reason = CompileWaitReason.queued if await self._has_runner(job) else CompileWaitReason.no_runner
        return CompileWaitInfo(reason, await self._position(job))

    async def _position(self, job: QueuedJob) -> int:
        # Порядок выдачи тот же, что у раннера: класс, виртуальное время справедливой очереди, постановка.
        queued = await self._queue.list(state=JobState.queued)
        key = (job.priority_class, job.vtime, job.queued_at, job.seq)
        ahead = sum(1 for other in queued if (other.priority_class, other.vtime, other.queued_at, other.seq) < key)
        return ahead + 1

    async def _has_runner(self, job: QueuedJob) -> bool:
        # После окна ожидания задачу берут только общие раннеры: чужие и свои личные здесь не в счёт.
        now = self._clock()
        return any(
            r.scope is RunnerScope.shared
            and r.revoked_at is None
            and runner_status(r, now) is RunnerStatus.online
            and job.tags <= r.tags
            for r in await self._runners.list()
        )


_FALLBACKS: dict[RouteReason, PlacementFallback] = {
    RouteReason.fallback_offline: PlacementFallback.offline,
    RouteReason.fallback_busy: PlacementFallback.busy,
    RouteReason.fallback_timeout: PlacementFallback.timeout,
    RouteReason.fallback_lost: PlacementFallback.lost,
    RouteReason.disabled: PlacementFallback.disabled,
}


def _owner_of(runner_owner_id: str | None, viewer_id: str | None) -> PlacementOwner:
    return PlacementOwner.me if viewer_id is not None and runner_owner_id == viewer_id else PlacementOwner.owner
