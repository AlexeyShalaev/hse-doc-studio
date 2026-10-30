"""InMemory-реализация IJobQueue на чистых правилах планировщика; часы подставляются в тестах."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hse_doc_studio.core.jobs.enums import JobState, JobStatus, RunnerErrorCode
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError, StaleAttemptError
from hse_doc_studio.core.jobs.queue import (
    EnqueueOutcome,
    EnqueueRequest,
    ExpiredOutcome,
    Heartbeat,
    QueuedJob,
    RunnerRef,
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


class InMemoryJobQueue:
    def __init__(self, clock: Callable[[], datetime] = _now) -> None:
        self._clock = clock
        self._jobs: dict[UUID, QueuedJob] = {}
        self._user_vtime: dict[UUID, float] = {}
        self._global_vtime = 0.0
        self._seq = 0
        # Последний опрос раннера и его число слотов: по ним решается аффинность.
        self._runners: dict[UUID, tuple[datetime, int]] = {}

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
        vtime = assign_vtime(self._user_vtime.get(request.user_id), self._global_vtime, request.cost, request.weight)
        self._user_vtime[request.user_id] = vtime
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
        )
        self._jobs[job.id] = job
        return EnqueueOutcome(job=job, superseded=tuple(superseded))

    async def claim(self, runner: RunnerRef, *, lease_s: float, quota: QueueQuota | None = None) -> QueuedJob | None:
        now = self._clock()
        self._runners[runner.id] = (now, runner.concurrency)
        limits = quota or QueueQuota()
        candidates = [
            job
            for job in self._jobs.values()
            if job.state is JobState.queued
            and job.tags <= runner.tags
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
        taken = replace(
            best,
            state=JobState.running,
            attempt=best.attempt + 1,
            runner_id=runner.id,
            lease_until=now + timedelta(seconds=lease_s),
            started_at=now,
        )
        self._jobs[taken.id] = taken
        self._global_vtime = advance_global_vtime(self._global_vtime, taken.vtime)
        return taken

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
        return sum(1 for j in self._jobs.values() if j.state is JobState.running and j.user_id == user_id)

    def _running_of_org(self, org_id: UUID | None) -> int | None:
        if org_id is None:
            return None
        return sum(1 for j in self._jobs.values() if j.state is JobState.running and j.org_id == org_id)

    def _affine_available(self, runner_id: UUID | None, now: datetime, lease_s: float) -> bool:
        if runner_id is None or runner_id not in self._runners:
            return False
        seen, concurrency = self._runners[runner_id]
        if now - seen > timedelta(seconds=lease_s):
            return False
        busy = sum(1 for j in self._jobs.values() if j.state is JobState.running and j.runner_id == runner_id)
        return busy < concurrency
