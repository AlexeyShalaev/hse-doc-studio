"""Задачи, которые не может взять ни один раннер: ждать с причиной или закончить понятным итогом.

Постановка уже отказывает, если подходящего раннера в сети нет. Но раннер может уйти после постановки:
его отозвали, поставили на паузу, он выключился, а у общих раннеров нужного тега (`office`) нет. Такая задача
раньше стояла в очереди вечно. Здесь её состояние считается по тем же правилам, что у отказа при постановке
(`RunnerFit`), и по таймеру она заканчивается как `failed` с кодом причины:

- раннера с тегами нет совсем (отозван, теги сняты): ждать нечего, короткий запас на гонку с регистрацией;
- подходящий раннер не в сети: запас на перезапуск и обновление раннера;
- подходящий раннер на паузе: ожидание осмысленно (паузу снимают одной кнопкой), поэтому оно дольше,
  а интерфейс всё это время показывает «ждёт раннер: раннер на паузе».

Если хоть один подходящий раннер в сети (пусть и занят), задача ждёт, как раньше: это очередь, а не отказ.
Окна ожидания, таймауты и фолбэк `personal_first` не трогаются: выдачу задачи по-прежнему решает очередь.
Время начала простоя хранится в памяти лидера: смена лидера только продлевает ожидание, раньше срока задача
не закончится.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from uuid import UUID

import structlog

from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import IJobQueue, QueuedJob
from hse_doc_studio.core.jobs.routing import IJobRouter, IPersonalRunnerSettings, JobRoute, RouteReason
from hse_doc_studio.core.jobs.runner_fit import RunnerFit, RunnerGapReason
from hse_doc_studio.core.jobs.runners import IRunnerRepository, Runner
from hse_doc_studio.use_cases.jobs.terminal import JobTerminalBroadcaster

logger = structlog.get_logger(__name__)

# Коды итога снятой задачи: те же, что видит человек в журнале сборки и в MCP.
NO_RUNNER_FOR_TAGS = "no_runner_for_tags"
RUNNER_PAUSED = "runner_paused"
RUNNER_OFFLINE = "runner_offline"

STRANDED_CODES: Mapping[RunnerGapReason, str] = MappingProxyType(
    {
        RunnerGapReason.no_runner: NO_RUNNER_FOR_TAGS,
        RunnerGapReason.personal_paused: RUNNER_PAUSED,
        RunnerGapReason.shared_paused: RUNNER_PAUSED,
        RunnerGapReason.personal_offline: RUNNER_OFFLINE,
        RunnerGapReason.shared_offline: RUNNER_OFFLINE,
    }
)

# Сколько задача ждёт без подходящего раннера в сети, прежде чем закончиться.
STRANDED_GRACE: Mapping[RunnerGapReason, timedelta] = MappingProxyType(
    {
        RunnerGapReason.no_runner: timedelta(minutes=1),
        RunnerGapReason.personal_offline: timedelta(minutes=5),
        RunnerGapReason.shared_offline: timedelta(minutes=5),
        RunnerGapReason.personal_paused: timedelta(minutes=30),
        RunnerGapReason.shared_paused: timedelta(minutes=30),
    }
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class QueuedJobFit:
    """Какие раннеры могут взять уже стоящую задачу и что с ними: по маршруту, который у неё записан."""

    def __init__(self, router: IJobRouter, settings: IPersonalRunnerSettings) -> None:
        self._router = router
        self._settings = settings

    async def personal_owner(self, job: QueuedJob) -> str | None:
        """Чьи личные раннеры могут взять задачу: так же, как решает выдача в очереди."""
        if job.route is JobRoute.pinned or not (await self._settings.current()).enabled:
            return None
        if job.route is JobRoute.personal_first:
            return job.route_owner_id
        if job.route is JobRoute.shared and job.route_reason is RouteReason.fallback_busy:
            # Ушла на общие из-за занятости: без общих с тегами её берёт личный раннер владельца.
            return await self._router.personal_owner(kind=job.kind, project_id=job.project_id, user_id=job.user_id)
        return None

    async def of(self, job: QueuedJob, runners: list[Runner], now: datetime) -> RunnerFit:
        return RunnerFit.of(job.tags, runners, now, personal_owner=await self.personal_owner(job))


class StrandedJobSweeper:
    def __init__(
        self,
        queue: IJobQueue,
        runners: IRunnerRepository,
        fit: QueuedJobFit,
        *,
        terminal: JobTerminalBroadcaster | None = None,
        clock: Callable[[], datetime] = _utc_now,
        grace: Mapping[RunnerGapReason, timedelta] = STRANDED_GRACE,
    ) -> None:
        self._queue = queue
        self._runners = runners
        self._fit = fit
        self._terminal = terminal or JobTerminalBroadcaster()
        self._clock = clock
        self._grace = grace
        # Задача -> когда впервые увидели, что взять её некому.
        self._since: dict[UUID, datetime] = {}

    async def sweep(self) -> tuple[QueuedJob, ...]:
        """Один проход: задачи без подходящего раннера дольше своего запаса заканчиваются как `failed`."""
        queued = [
            job
            for job in await self._queue.list(state=JobState.queued)
            if job.route is not JobRoute.pinned and job.kind is not JobKind.ai_relay
        ]
        if not queued:
            self._since.clear()
            return ()
        now = self._clock()
        runners = await self._runners.list()
        stranded: set[UUID] = set()
        failed: list[QueuedJob] = []
        for job in queued:
            reason = (await self._fit.of(job, runners, now)).reason
            if reason is None:
                continue
            stranded.add(job.id)
            since = self._since.setdefault(job.id, now)
            if now - since < self._grace[reason]:
                continue
            done = await self._queue.fail_queued(job.id, STRANDED_CODES[reason])
            if done is None:
                continue
            stranded.discard(job.id)
            failed.append(done)
            logger.warning(
                "job_no_suitable_runner",
                job_id=str(job.id),
                kind=job.kind.value,
                tags=sorted(job.tags),
                reason=reason.value,
                waited_s=int((now - since).total_seconds()),
            )
        self._since = {job_id: at for job_id, at in self._since.items() if job_id in stranded}
        await self._terminal.emit_all(failed)
        return tuple(failed)
