"""Раннер берёт и держит задачу: долгий опрос, выдача конверта с токеном задачи, heartbeat."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from hse_doc_studio.core.jobs.codec import decode_envelope
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError, StaleAttemptError
from hse_doc_studio.core.jobs.queue import IJobQueue, QueuedJob, RunnerRef
from hse_doc_studio.core.jobs.routing import IPersonalRunnerSettings, RunnerScope
from hse_doc_studio.core.jobs.runners import IRunnerRepository, JobTokenSigner, Runner
from hse_doc_studio.core.jobs.scheduler import QueueQuota
from hse_doc_studio.core.jobs.wire import (
    FEATURE_AI_RELAY,
    HeartbeatResponse,
    JobEnvelope,
    PollRequest,
    PollResponse,
)
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

POLL_INTERVAL_S = 1.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RunnerJobService:
    def __init__(
        self,
        queue: IJobQueue,
        queue_service: JobQueueService,
        runners: IRunnerRepository,
        signer: JobTokenSigner,
        wakeup: JobWakeup,
        *,
        lease_s: float,
        timeout_grace_s: float,
        poll_interval_s: float = POLL_INTERVAL_S,
        clock: Callable[[], datetime] = _utc_now,
        quota_source: Callable[[], Awaitable[QueueQuota | None]] | None = None,
        personal_settings: IPersonalRunnerSettings | None = None,
    ) -> None:
        self._personal_settings = personal_settings
        self._queue = queue
        self._service = queue_service
        self._runners = runners
        self._signer = signer
        self._wakeup = wakeup
        self._lease_s = lease_s
        self._grace_s = timeout_grace_s
        self._interval = poll_interval_s
        self._clock = clock
        self._quota_source = quota_source

    async def poll(self, runner: Runner, request: PollRequest) -> PollResponse:
        """Держит запрос до `wait_s`: отвечает, как только появилась подходящая задача, иначе пустым ответом.

        Раннер на паузе работы не получает, но опрос принимается: он остаётся живым для админки.
        """
        deadline = time.monotonic() + request.wait_s
        while True:
            await self._runners.touch(runner.id, self._clock())
            # Снимок раннера взят при входе, а опрос долгий: пауза, отзыв и выключение могли случиться за это время.
            current = await self._runners.get(runner.id)
            if current is None or current.revoked_at is not None:
                return PollResponse()
            if not current.paused and await self._may_work(current):
                ref = self._ref(current, request)
                quota = (
                    await self._quota_source()
                    if self._quota_source is not None and ref.scope is RunnerScope.shared
                    else None
                )
                job = await self._queue.claim(ref, lease_s=self._lease_s, quota=quota)
                if job is not None:
                    return PollResponse(envelope=self._envelope(job, current))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return PollResponse()
            await self._wakeup.wait(min(remaining, self._interval))

    async def heartbeat(self, runner: Runner, job_id: UUID, attempt: int, job_token: str) -> HeartbeatResponse:
        self._signer.verify(job_token, self._clock(), job_id=str(job_id), runner_id=runner.id)
        job = await self._queue.get(job_id)
        if job is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        if job.runner_id is None or job.runner_id.hex != UUID(runner.id).hex:
            raise StaleAttemptError(f"job {job_id} is not leased to this runner")
        await self._runners.touch(runner.id, self._clock())
        beat = await self._service.heartbeat(job_id, attempt)
        return HeartbeatResponse(cancel=beat.cancel, lease_until=beat.lease_until)

    async def _may_work(self, runner: Runner) -> bool:
        """Личный раннер при выключенных в установке личных раннерах опрашивает, но работы не получает."""
        if runner.scope is not RunnerScope.personal or self._personal_settings is None:
            return True
        return (await self._personal_settings.current()).enabled

    @staticmethod
    def _ref(runner: Runner, request: PollRequest) -> RunnerRef:
        """Область и хозяин из записи раннера, а не из запроса: раннер сам себе область не назначает."""
        return RunnerRef(
            id=UUID(runner.id),
            tags=runner.tags,
            concurrency=runner.concurrency,
            scope=runner.scope,
            owner_id=runner.owner_id,
            accept_jobs=request.free_slots > 0,
            accept_relay=request.free_ai_slots > 0 and FEATURE_AI_RELAY in runner.features,
        )

    def _envelope(self, job: QueuedJob, runner: Runner) -> JobEnvelope:
        """Конверт из снимка постановки: к нему добавляются номер попытки и токен задачи для этого раннера.

        Таймаут берётся из записи очереди: у личного раннера там предел без квоты установки. Личный раннер
        не получает e-mail актора, гостевую ссылку и признак админа: машине владельца они не нужны.
        """
        expires_at = self._clock() + timedelta(seconds=job.timeout_s + self._grace_s + self._lease_s)
        token = self._signer.sign(str(job.id), runner.id, expires_at, job.attempt)
        payload: dict[str, Any] = {**job.payload, "timeout_s": job.timeout_s}
        if runner.scope is RunnerScope.personal:
            spec = dict(payload["spec"])
            spec["actor"] = {**spec["actor"], "email": None, "link_id": None, "is_instance_admin": False}
            payload["spec"] = spec
        return decode_envelope({**payload, "attempt": job.attempt, "job_token": token})
