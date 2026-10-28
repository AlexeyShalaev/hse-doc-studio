"""Порт очереди задач серверного режима.

Очередь знает только порядок, аренды и состояния; что делать с результатом, решают хуки диспетчера.
Реализации: память (`InMemoryJobQueue` в тестах) и Postgres (`SKIP LOCKED`), обе проходят один контрактный набор.
Время всегда берёт сама реализация из своих часов.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.enums import JobKind, JobPriorityClass, JobState, JobStatus
from hse_doc_studio.core.jobs.scheduler import QueueQuota


@dataclass(frozen=True)
class EnqueueRequest:
    """Что поставить: само задание в `payload` (проводная форма конверта без токена) и поля порядка."""

    job_id: UUID
    kind: JobKind
    project_id: UUID
    user_id: UUID
    tags: frozenset[str]
    payload: dict[str, Any]
    org_id: UUID | None = None
    priority_class: JobPriorityClass = JobPriorityClass.checks
    coalesce_key: str | None = None
    cost: float = 1.0
    weight: float = 1.0
    max_attempts: int = 1
    timeout_s: float = 600.0
    # Раннер, который последним собирал этот проект: у него тёплый кэш.
    affinity_runner_id: UUID | None = None


@dataclass(frozen=True)
class QueuedJob:
    """Снимок записи очереди."""

    id: UUID
    kind: JobKind
    project_id: UUID
    user_id: UUID
    org_id: UUID | None
    tags: frozenset[str]
    priority_class: JobPriorityClass
    vtime: float
    queued_at: datetime
    state: JobState
    attempt: int
    max_attempts: int
    timeout_s: float
    payload: dict[str, Any]
    coalesce_key: str | None = None
    affinity_runner_id: UUID | None = None
    runner_id: UUID | None = None
    lease_until: datetime | None = None
    # Начало текущей попытки: от него считается таймаут задачи.
    started_at: datetime | None = None
    cancel_requested: bool = False
    finished_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    # Порядковый номер постановки: разрешает равные метки и время.
    seq: int = 0


@dataclass(frozen=True)
class EnqueueOutcome:
    job: QueuedJob
    # Не начатые задачи с тем же ключом склейки, которые эта заменила.
    superseded: tuple[QueuedJob, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RunnerRef:
    """Кто просит работу: теги отбирают подходящие задачи, `concurrency` нужен для аффинности."""

    id: UUID
    tags: frozenset[str]
    concurrency: int = 1


@dataclass(frozen=True)
class Heartbeat:
    cancel: bool
    lease_until: datetime


@dataclass(frozen=True)
class ExpiredOutcome:
    """Что сделал сборщик просроченных аренд с одной задачей: вернул в очередь или закончил."""

    job: QueuedJob
    requeued: bool


class IJobQueue(Protocol):
    async def enqueue(self, request: EnqueueRequest) -> EnqueueOutcome:
        """Поставить задачу и в той же операции отменить не начатые с тем же ключом склейки (`superseded`)."""
        ...

    async def claim(self, runner: RunnerRef, *, lease_s: float, quota: QueueQuota | None = None) -> QueuedJob | None:
        """Лучшая подходящая задача: класс, метка, время. Пользователи на пределе квоты пропускаются, остальные идут."""
        ...

    async def heartbeat(self, job_id: UUID, attempt: int, *, lease_s: float) -> Heartbeat:
        """Продлить аренду; `StaleAttemptError`, если попытка уже не текущая."""
        ...

    async def complete(
        self,
        job_id: UUID,
        attempt: int,
        status: JobStatus,
        *,
        result: dict[str, Any] | None = None,
        error_code: str | None = None,
    ) -> QueuedJob:
        """Закончить попытку; `StaleAttemptError` для чужой или просроченной."""
        ...

    async def request_cancel(self, job_id: UUID) -> QueuedJob:
        """Не начатая задача отменяется сразу, идущая получает флаг и узнаёт о нём в heartbeat."""
        ...

    async def requeue_expired(self) -> tuple[ExpiredOutcome, ...]:
        """Задачи с истёкшей арендой: назад в очередь, пока остались попытки, иначе `failed` с `runner_lost`."""
        ...

    async def get(self, job_id: UUID) -> QueuedJob | None: ...

    async def list(self, *, state: JobState | None = None, project_id: UUID | None = None) -> tuple[QueuedJob, ...]: ...
