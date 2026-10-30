"""Жизненный цикл задач очереди над репозиторием: аренды, повторы, таймауты и отмена.

Очередь знает только состояния и аренды. Здесь правила, которые от неё нужны серверу: heartbeat раннера,
сборщик просроченных аренд, наблюдатель таймаутов и приведение итога по таймауту к `timed_out`.
Время берётся из тех же часов, что у очереди, поэтому сценарии с арендами проверяются поддельными часами.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import structlog

from hse_doc_studio.core.jobs.enums import JobState, JobStatus
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError, StaleAttemptError
from hse_doc_studio.core.jobs.queue import ExpiredOutcome, Heartbeat, IJobQueue, QueuedJob
from hse_doc_studio.core.jobs.routing import RouteReason
from hse_doc_studio.use_cases.jobs.terminal import JobTerminalBroadcaster
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

logger = structlog.get_logger(__name__)

LEASE_S = 45.0
TIMEOUT_GRACE_S = 15.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class TimeoutSweep:
    """Что сделал наблюдатель таймаутов за один проход."""

    # Задачам просрочившим срок отправлена отмена: раннер узнает о ней в heartbeat.
    cancelled: tuple[QueuedJob, ...] = field(default_factory=tuple)
    # Задачи, которые раннер не остановил за время на остановку: закончены как `timed_out`.
    timed_out: tuple[QueuedJob, ...] = field(default_factory=tuple)


class JobQueueService:
    def __init__(
        self,
        queue: IJobQueue,
        *,
        lease_s: float = LEASE_S,
        timeout_grace_s: float = TIMEOUT_GRACE_S,
        clock: Callable[[], datetime] = _utc_now,
        wakeup: JobWakeup | None = None,
        terminal: JobTerminalBroadcaster | None = None,
    ) -> None:
        self._wakeup = wakeup
        self._terminal = terminal or JobTerminalBroadcaster()
        self._queue = queue
        self._lease_s = lease_s
        self._grace = timedelta(seconds=timeout_grace_s)
        self._clock = clock

    async def heartbeat(self, job_id: UUID, attempt: int) -> Heartbeat:
        """Продлевает аренду; отмену получает и задача, которая просрочила таймаут."""
        beat = await self._queue.heartbeat(job_id, attempt, lease_s=self._lease_s)
        if beat.cancel:
            return beat
        job = await self._queue.get(job_id)
        if job is not None and self._overdue(job):
            return Heartbeat(cancel=True, lease_until=beat.lease_until)
        return beat

    async def complete(
        self,
        job_id: UUID,
        attempt: int,
        status: JobStatus,
        *,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> QueuedJob:
        """Завершение с ограждением по попытке: чужая или просроченная получает `StaleAttemptError`.

        Раннер, остановленный по таймауту, сообщает `cancelled`; итог по задаче при этом `timed_out`.
        """
        job = await self._queue.get(job_id)
        if job is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        if status is JobStatus.cancelled and job.state is JobState.running and self._overdue(job):
            status = JobStatus.timed_out
        done = await self._queue.complete(job_id, attempt, status, result=result, error_code=error_code)
        await self._terminal.emit(done)
        return done

    async def cancel(self, job_id: UUID) -> QueuedJob:
        """Не начатая задача отменяется сразу, идущая получает флаг для heartbeat."""
        job = await self._queue.request_cancel(job_id)
        await self._terminal.emit(job)
        return job

    async def expire_personal_wait(
        self,
        *,
        owner_id: str | None = None,
        project_id: UUID | None = None,
        reason: RouteReason = RouteReason.fallback_offline,
    ) -> int:
        """Ждущие личный раннер сборки сразу становятся доступны общим раннерам; общие будятся."""
        count = await self._queue.expire_personal_wait(owner_id=owner_id, project_id=project_id, reason=reason)
        if count and self._wakeup is not None:
            self._wakeup.notify()
        return count

    async def cancel_pinned(self, *, runner_id: UUID | None, error_code: str) -> tuple[QueuedJob, ...]:
        """Ждущие ретрансляции раннера (или все) отменяются; слушатели закрывают каналы."""
        cancelled = await self._queue.cancel_pinned(runner_id=runner_id, error_code=error_code)
        await self._terminal.emit_all(cancelled)
        return cancelled

    async def reap(self) -> tuple[ExpiredOutcome, ...]:
        """Возвращает в очередь задачи с истёкшей арендой, пока остались попытки, иначе `runner_lost`."""
        outcomes = await self._queue.requeue_expired()
        for outcome in outcomes:
            logger.warning(
                "job_lease_expired",
                job_id=str(outcome.job.id),
                attempt=outcome.job.attempt,
                requeued=outcome.requeued,
                state=outcome.job.state.value,
            )
        if self._wakeup is not None and any(outcome.requeued for outcome in outcomes):
            self._wakeup.notify()
        await self._terminal.emit_all([outcome.job for outcome in outcomes if not outcome.requeued])
        return outcomes

    async def enforce_timeouts(self) -> TimeoutSweep:
        """Сначала просит раннер остановить задачу, а если он не успел за время на остановку, заканчивает её сама."""
        now = self._clock()
        cancelled: list[QueuedJob] = []
        timed_out: list[QueuedJob] = []
        for job in await self._queue.list(state=JobState.running):
            deadline = self._deadline(job)
            if deadline is None or deadline > now:
                continue
            try:
                if deadline + self._grace <= now:
                    timed_out.append(await self._queue.complete(job.id, job.attempt, JobStatus.timed_out))
                elif not job.cancel_requested:
                    cancelled.append(await self._queue.request_cancel(job.id))
            except StaleAttemptError:
                continue
        await self._terminal.emit_all(timed_out)
        if cancelled or timed_out:
            logger.warning(
                "job_timeouts", cancelled=[str(j.id) for j in cancelled], timed_out=[str(j.id) for j in timed_out]
            )
        return TimeoutSweep(cancelled=tuple(cancelled), timed_out=tuple(timed_out))

    async def sweep(self) -> None:
        """Один проход периодической задачи: сначала аренды, потом таймауты."""
        await self.reap()
        await self.enforce_timeouts()

    def _deadline(self, job: QueuedJob) -> datetime | None:
        if job.started_at is None:
            return None
        return job.started_at + timedelta(seconds=job.timeout_s)

    def _overdue(self, job: QueuedJob) -> bool:
        deadline = self._deadline(job)
        return deadline is not None and deadline <= self._clock()
