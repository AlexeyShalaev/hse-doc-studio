"""InMemory-реализация IJobQueue на чистых правилах планировщика; часы подставляются в тестах."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hse_doc_studio.core.jobs.enums import JobKind, JobState, JobStatus, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError, StaleAttemptError
from hse_doc_studio.core.jobs.queue import (
    EnqueueOutcome,
    EnqueueRequest,
    ExpiredOutcome,
    Heartbeat,
    QueuedJob,
    RunnerRef,
)
from hse_doc_studio.core.jobs.registry import build_job_kinds
from hse_doc_studio.core.jobs.routing import (
    KEPT_FALLBACK_REASONS,
    JobRoute,
    ProjectBuildRunners,
    ProjectRouteInfo,
    RouteReason,
    RunnerScope,
)
from hse_doc_studio.core.jobs.scheduler import (
    QueueQuota,
    advance_global_vtime,
    affinity_allows,
    assign_vtime,
    caps_allow,
    retry_available,
)


def _now() -> datetime:
    return datetime.now(UTC)


_PERSONAL_KINDS = frozenset(spec.kind for spec in build_job_kinds() if spec.policy.personal_runner_allowed)


def _uuid_or_none(value: str | None) -> UUID | None:
    try:
        return UUID(value) if value is not None else None
    except ValueError:
        return None


class InMemoryJobQueue:
    def __init__(self, clock: Callable[[], datetime] = _now) -> None:
        self._clock = clock
        self._jobs: dict[UUID, QueuedJob] = {}
        self._user_vtime: dict[UUID, float] = {}
        self._global_vtime = 0.0
        self._seq = 0
        # Последний опрос раннера и его число слотов: по ним решается аффинность.
        self._runners: dict[UUID, tuple[datetime, int]] = {}
        # Каталог проектов для выдачи личным раннерам: в Postgres это таблица projects.
        self._projects: dict[UUID, ProjectRouteInfo] = {}

    def set_project(self, info: ProjectRouteInfo) -> None:
        self._projects[info.project_id] = info

    @property
    def global_vtime(self) -> float:
        return self._global_vtime

    async def enqueue(self, request: EnqueueRequest) -> EnqueueOutcome:
        now = self._clock()
        superseded: list[QueuedJob] = []
        if request.coalesce_key is not None:
            for job in list(self._jobs.values()):
                if job.state is JobState.queued and job.coalesce_key == request.coalesce_key:
                    done = replace(
                        job,
                        state=JobState.cancelled,
                        finished_at=now,
                        error_code=RunnerErrorCode.superseded.value,
                    )
                    self._jobs[job.id] = done
                    superseded.append(done)
                elif job.state is JobState.running and job.coalesce_key == request.coalesce_key:
                    self._jobs[job.id] = replace(job, cancel_requested=True)
        if request.fair_share:
            vtime = assign_vtime(
                self._user_vtime.get(request.user_id), self._global_vtime, request.cost, request.weight
            )
            self._user_vtime[request.user_id] = vtime
            vcost = request.cost / request.weight
        else:
            vtime, vcost = self._global_vtime, 0.0
        self._seq += 1
        job = QueuedJob(
            id=request.job_id,
            kind=request.kind,
            project_id=request.project_id,
            user_id=request.user_id,
            org_id=request.org_id,
            tags=request.tags,
            priority_class=request.priority_class,
            vtime=vtime,
            queued_at=now,
            state=JobState.queued,
            attempt=0,
            max_attempts=request.max_attempts,
            timeout_s=request.timeout_s,
            payload=request.payload,
            coalesce_key=request.coalesce_key,
            affinity_runner_id=request.affinity_runner_id,
            seq=self._seq,
            route=request.route,
            route_owner_id=request.route_owner_id,
            personal_until=request.personal_until,
            target_runner_id=request.target_runner_id,
            route_reason=request.route_reason,
            vcost=vcost,
            timeout_personal_s=request.timeout_personal_s,
        )
        self._jobs[job.id] = job
        return EnqueueOutcome(job=job, superseded=tuple(superseded))

    async def claim(self, runner: RunnerRef, *, lease_s: float, quota: QueueQuota | None = None) -> QueuedJob | None:
        now = self._clock()
        self._runners[runner.id] = (now, runner.concurrency)
        if runner.scope is RunnerScope.personal:
            return self._claim_personal(runner, now, lease_s)
        if not runner.accept_jobs:
            return None
        limits = quota or QueueQuota()
        candidates = [
            job
            for job in self._jobs.values()
            if job.state is JobState.queued
            and job.tags <= runner.tags
            and job.kind is not JobKind.ai_relay
            and (
                job.route is JobRoute.shared
                or (
                    job.route is JobRoute.personal_first
                    and job.personal_until is not None
                    and job.personal_until <= now
                )
            )
            and caps_allow(
                self._running_of_user(job.user_id),
                self._running_of_org(job.org_id),
                limits,
                user_id=job.user_id,
                org_id=job.org_id,
            )
            and affinity_allows(
                job.affinity_runner_id,
                job.queued_at,
                runner.id,
                now,
                affine_available=self._affine_available(job.affinity_runner_id, now, lease_s),
            )
        ]
        if not candidates:
            return None
        best = min(candidates, key=lambda j: (j.priority_class, j.vtime, j.queued_at, j.seq))
        reason = best.route_reason
        if best.route is JobRoute.personal_first and reason not in KEPT_FALLBACK_REASONS:
            reason = RouteReason.fallback_timeout
        taken = replace(
            best,
            state=JobState.running,
            attempt=best.attempt + 1,
            runner_id=runner.id,
            lease_until=now + timedelta(seconds=lease_s),
            started_at=now,
            runner_scope=RunnerScope.shared,
            route_reason=reason,
        )
        self._jobs[taken.id] = taken
        self._global_vtime = advance_global_vtime(self._global_vtime, taken.vtime)
        return taken

    def _claim_personal(self, runner: RunnerRef, now: datetime, lease_s: float) -> QueuedJob | None:
        owner = runner.owner_id
        owner_uuid = _uuid_or_none(owner)
        candidates = [
            job
            for job in self._jobs.values()
            if job.state is JobState.queued
            and job.tags <= runner.tags
            and (
                (runner.accept_jobs and self._personal_build_allowed(job, owner, owner_uuid))
                or (
                    runner.accept_relay
                    and job.route is JobRoute.pinned
                    and job.target_runner_id == runner.id
                    and job.kind is JobKind.ai_relay
                    and owner_uuid is not None
                    and job.user_id == owner_uuid
                )
            )
        ]
        if not candidates:
            return None
        best = min(candidates, key=lambda j: (j.priority_class, j.vtime, j.queued_at, j.seq))
        timeout_s, kept = best.timeout_s, best.timeout_personal_s
        if kept is not None:
            # Предел без квоты на время личной попытки; предел с квотой ждёт возврата в очередь.
            timeout_s, kept = kept, timeout_s
        taken = replace(
            best,
            state=JobState.running,
            attempt=best.attempt + 1,
            runner_id=runner.id,
            lease_until=now + timedelta(seconds=lease_s),
            started_at=now,
            runner_scope=RunnerScope.personal,
            route_reason=RouteReason.pinned if best.route is JobRoute.pinned else RouteReason.personal,
            timeout_s=timeout_s,
            timeout_personal_s=kept,
        )
        self._jobs[taken.id] = taken
        # Личный раннер не двигает глобальное время и возвращает метку справедливости.
        if best.vcost and best.user_id in self._user_vtime:
            self._user_vtime[best.user_id] = max(self._user_vtime[best.user_id] - best.vcost, 0.0)
        return taken

    def _personal_build_allowed(self, job: QueuedJob, owner: str | None, owner_uuid: UUID | None) -> bool:
        if owner is None or job.route is not JobRoute.personal_first or job.route_owner_id != owner:
            return False
        if job.kind not in _PERSONAL_KINDS:
            return False
        project = self._projects.get(job.project_id)
        if project is None or project.deleted or project.owner_user_id != owner:
            return False
        return (
            owner_uuid is not None and job.user_id == owner_uuid
        ) or project.build_runners is ProjectBuildRunners.owner

    async def expire_personal_wait(
        self,
        *,
        owner_id: str | None = None,
        project_id: UUID | None = None,
        reason: RouteReason = RouteReason.fallback_offline,
    ) -> int:
        now = self._clock()
        count = 0
        for job in list(self._jobs.values()):
            if (
                job.state is JobState.queued
                and job.route is JobRoute.personal_first
                and job.personal_until is not None
                and job.personal_until > now
                and (owner_id is None or job.route_owner_id == owner_id)
                and (project_id is None or job.project_id == project_id)
            ):
                self._jobs[job.id] = replace(job, personal_until=now, route_reason=reason)
                count += 1
        return count

    async def cancel_pinned(self, *, runner_id: UUID | None, error_code: str) -> tuple[QueuedJob, ...]:
        now = self._clock()
        done: list[QueuedJob] = []
        for job in list(self._jobs.values()):
            if (
                job.state is JobState.queued
                and job.route is JobRoute.pinned
                and (runner_id is None or job.target_runner_id == runner_id)
            ):
                cancelled = replace(
                    job, state=JobState.cancelled, finished_at=now, cancel_requested=True, error_code=error_code
                )
                self._jobs[job.id] = cancelled
                done.append(cancelled)
        return tuple(done)

    async def heartbeat(self, job_id: UUID, attempt: int, *, lease_s: float) -> Heartbeat:
        job = self._current(job_id, attempt)
        lease_until = self._clock() + timedelta(seconds=lease_s)
        self._jobs[job_id] = replace(job, lease_until=lease_until)
        return Heartbeat(cancel=job.cancel_requested, lease_until=lease_until)

    async def complete(
        self,
        job_id: UUID,
        attempt: int,
        status: JobStatus,
        *,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> QueuedJob:
        job = self._current(job_id, attempt)
        if job.cancel_requested and status is JobStatus.succeeded:
            status, result, error_code = JobStatus.cancelled, None, None
        done = replace(
            job,
            state=JobState.of_status(status),
            finished_at=self._clock(),
            lease_until=None,
            result=result,
            error_code=error_code,
        )
        self._jobs[job_id] = done
        return done

    async def request_cancel(self, job_id: UUID) -> QueuedJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        if job.state is JobState.queued:
            job = replace(job, state=JobState.cancelled, finished_at=self._clock(), cancel_requested=True)
        elif job.state is JobState.running:
            job = replace(job, cancel_requested=True)
        self._jobs[job_id] = job
        return job

    async def requeue_expired(self) -> tuple[ExpiredOutcome, ...]:
        now = self._clock()
        outcomes: list[ExpiredOutcome] = []
        for job in list(self._jobs.values()):
            if job.state is not JobState.running or job.lease_until is None or job.lease_until > now:
                continue
            if job.cancel_requested:
                done = replace(job, state=JobState.cancelled, finished_at=now, lease_until=None)
                outcomes.append(ExpiredOutcome(done, requeued=False))
            elif retry_available(job.attempt, job.max_attempts):
                done = replace(
                    job,
                    state=JobState.queued,
                    runner_id=None,
                    lease_until=None,
                    started_at=None,
                    affinity_runner_id=None,
                    runner_scope=None,
                )
                if job.runner_scope is RunnerScope.personal:
                    # Личный раннер пропал: повтор где угодно, предел с квотой возвращается.
                    done = replace(
                        done,
                        personal_until=now if job.route is JobRoute.personal_first else job.personal_until,
                        route_reason=RouteReason.fallback_lost,
                        timeout_s=job.timeout_personal_s if job.timeout_personal_s is not None else job.timeout_s,
                        timeout_personal_s=job.timeout_s if job.timeout_personal_s is not None else None,
                    )
                outcomes.append(ExpiredOutcome(done, requeued=True))
            else:
                done = replace(
                    job,
                    state=JobState.failed,
                    finished_at=now,
                    lease_until=None,
                    error_code=RunnerErrorCode.runner_lost.value,
                )
                outcomes.append(ExpiredOutcome(done, requeued=False))
            self._jobs[job.id] = done
        return tuple(outcomes)

    async def get(self, job_id: UUID) -> QueuedJob | None:
        return self._jobs.get(job_id)

    async def list(self, *, state: JobState | None = None, project_id: UUID | None = None) -> tuple[QueuedJob, ...]:
        return tuple(
            job
            for job in self._jobs.values()
            if (state is None or job.state is state) and (project_id is None or job.project_id == project_id)
        )

    def _current(self, job_id: UUID, attempt: int) -> QueuedJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        if job.state is not JobState.running or job.attempt != attempt:
            raise StaleAttemptError(f"attempt {attempt} of job {job_id} is not current")
        return job

    def _running_of_user(self, user_id: UUID) -> int:
        return sum(
            1
            for j in self._jobs.values()
            if j.state is JobState.running and j.user_id == user_id and j.runner_scope is RunnerScope.shared
        )

    def _running_of_org(self, org_id: UUID | None) -> int | None:
        if org_id is None:
            return None
        return sum(
            1
            for j in self._jobs.values()
            if j.state is JobState.running and j.org_id == org_id and j.runner_scope is RunnerScope.shared
        )

    def _affine_available(self, runner_id: UUID | None, now: datetime, lease_s: float) -> bool:
        if runner_id is None or runner_id not in self._runners:
            return False
        seen, concurrency = self._runners[runner_id]
        if now - seen > timedelta(seconds=lease_s):
            return False
        busy = sum(1 for j in self._jobs.values() if j.state is JobState.running and j.runner_id == runner_id)
        return busy < concurrency
