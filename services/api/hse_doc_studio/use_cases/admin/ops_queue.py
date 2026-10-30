"""Очередь задач в админке: список с фильтрами, сводка, отмена и пикер проектов. Отмена попадает в журнал аудита."""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.admin import (
    IAdminProjectPicker,
    IJobAdminReader,
    JobAdminFilter,
    JobAdminPage,
    JobListing,
    QueueStats,
)
from hse_doc_studio.core.jobs.errors import QueuedJobNotFoundError
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.listing import MAX_PAGE_LIMIT, PICKER_LIMIT, PickerResult, clamp_limit
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService

MAX_JOBS_PAGE = MAX_PAGE_LIMIT


class ListQueueUC:
    def __init__(self, reader: IJobAdminReader) -> None:
        self._reader = reader

    async def execute(
        self, actor: Actor, flt: JobAdminFilter, *, before_seq: int | None = None, limit: int = 50
    ) -> JobAdminPage:
        require_admin(actor)
        return await self._reader.list_jobs(flt, before_seq=before_seq, limit=max(1, min(limit, MAX_JOBS_PAGE)))


class QueueSummaryUC:
    def __init__(self, reader: IJobAdminReader, *, clock: Clock = utc_now) -> None:
        self._reader = reader
        self._clock = clock

    async def execute(self, actor: Actor) -> QueueStats:
        require_admin(actor)
        return await self._reader.stats(self._clock())


class CancelJobUC:
    def __init__(
        self,
        queue: IJobQueue,
        service: JobQueueService,
        audit: IAuditLog,
        uow: IUnitOfWork,
        reader: IJobAdminReader,
    ) -> None:
        self._queue = queue
        self._service = service
        self._audit = audit
        self._uow = uow
        self._reader = reader

    async def execute(self, actor: Actor, job_id: UUID) -> JobListing:
        """Законченная задача остаётся как есть и в журнал не пишется: отменять нечего."""
        admin_id = require_admin(actor)
        before = await self._queue.get(job_id)
        if before is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        if not before.state.is_terminal:
            async with self._uow.begin():
                await self._service.cancel(job_id)
                await self._audit.record(
                    "queue.job_cancel",
                    actor_id=admin_id,
                    target=str(job_id),
                    details={"kind": before.kind.value, "state": before.state.value, "user_id": str(before.user_id)},
                )
        # Ответ в той же форме, что строка списка: с подписями человека, проекта и раннера.
        found = await self._reader.get(job_id)
        if found is None:
            raise QueuedJobNotFoundError(f"job {job_id} not found")
        return found


class PickProjectsUC:
    def __init__(self, picker: IAdminProjectPicker) -> None:
        self._picker = picker

    async def execute(self, actor: Actor, q: str | None, limit: int = PICKER_LIMIT) -> PickerResult:
        require_admin(actor)
        return await self._picker.pick(q, clamp_limit(limit, PICKER_LIMIT))
