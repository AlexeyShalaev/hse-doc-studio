"""Чтение очереди и раннеров для админки: статус раннера по последнему опросу, фильтры, сводка очереди.

Порядок и аренды остаются у `IJobQueue`; здесь только то, что нужно экранам админа и не нужно раннеру.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.enums import JobKind, JobState
from hse_doc_studio.core.jobs.queue import QueuedJob
from hse_doc_studio.core.jobs.routing import RunnerScope
from hse_doc_studio.core.jobs.runners import Runner

# Долгий опрос раннера длится до 25 с: молчание дольше минуты уже подозрительно, дольше пяти минут означает потерю.
RUNNER_ONLINE_WITHIN = timedelta(seconds=60)
RUNNER_STALE_WITHIN = timedelta(minutes=5)


class RunnerStatus(StrEnum):
    online = "online"
    stale = "stale"
    offline = "offline"
    paused = "paused"
    revoked = "revoked"
    # Личный раннер, когда личные раннеры выключены в установке.
    disabled = "disabled"


def runner_status(  # noqa: PLR0911 — порядок проверок закреплён спецификацией
    runner: Runner, now: datetime, *, personal_enabled: bool = True
) -> RunnerStatus:
    """Отзыв, выключение и пауза важнее давности опроса: на паузе раннер опрашивает, но работу не получает.

    Мягкий уход (`POST /offline`) делает раннер не в сети сразу, пока он снова не опросит сервер.
    """
    if runner.revoked_at is not None:
        return RunnerStatus.revoked
    if runner.scope is RunnerScope.personal and not personal_enabled:
        return RunnerStatus.disabled
    if runner.paused:
        return RunnerStatus.paused
    if runner.offline_at is not None and (runner.last_seen_at is None or runner.offline_at >= runner.last_seen_at):
        return RunnerStatus.offline
    if runner.last_seen_at is None:
        return RunnerStatus.offline
    silence = now - runner.last_seen_at
    if silence <= RUNNER_ONLINE_WITHIN:
        return RunnerStatus.online
    return RunnerStatus.stale if silence <= RUNNER_STALE_WITHIN else RunnerStatus.offline


@dataclass(frozen=True)
class JobAdminFilter:
    state: JobState | None = None
    kind: JobKind | None = None
    user_id: UUID | None = None
    project_id: UUID | None = None
    # Кто взял задачу: общие или личные раннеры.
    runner_scope: RunnerScope | None = None


@dataclass(frozen=True)
class JobAdminPage:
    items: tuple[QueuedJob, ...]
    # Курсор следующей страницы: `seq` последней записи, пока есть ещё.
    next_before_seq: int | None = None


@dataclass(frozen=True)
class QueueStats:
    by_state: dict[JobState, int] = field(default_factory=dict)
    queued_by_class: dict[int, int] = field(default_factory=dict)
    oldest_queued_at: datetime | None = None
    # Ожидание в очереди задач, начавшихся за последний час; None, если таких не было.
    wait_p50_s: float | None = None
    wait_p95_s: float | None = None


class IJobAdminReader(Protocol):
    async def list_jobs(self, flt: JobAdminFilter, *, before_seq: int | None, limit: int) -> JobAdminPage:
        """Новые записи первыми; `before_seq` продолжает список с места, где остановилась прошлая страница."""
        ...

    async def stats(self, now: datetime) -> QueueStats: ...
