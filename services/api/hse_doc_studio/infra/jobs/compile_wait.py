"""Причина ожидания сборки по записи очереди: место в очереди, нет раннера, потерянный раннер, замена."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.compile.wait import CompileWaitInfo, CompileWaitReason
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status
from hse_doc_studio.core.jobs.enums import JobState, RunnerErrorCode
from hse_doc_studio.core.jobs.queue import IJobQueue, QueuedJob
from hse_doc_studio.core.jobs.runners import IRunnerRepository


class QueueCompileWaitReader:
    enabled = True

    def __init__(self, queue: IJobQueue, runners: IRunnerRepository, *, clock: Clock = utc_now) -> None:
        self._queue = queue
        self._runners = runners
        self._clock = clock

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
        reason = CompileWaitReason.queued if await self._has_runner(job) else CompileWaitReason.no_runner
        return CompileWaitInfo(reason, await self._position(job))

    async def _position(self, job: QueuedJob) -> int:
        queued = await self._queue.list(state=JobState.queued)
        ahead = sum(1 for other in queued if (other.priority_class, other.seq) < (job.priority_class, job.seq))
        return ahead + 1

    async def _has_runner(self, job: QueuedJob) -> bool:
        now = self._clock()
        return any(
            r.revoked_at is None and runner_status(r, now) is RunnerStatus.online and job.tags <= r.tags
            for r in await self._runners.list()
        )
