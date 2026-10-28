"""Провайдер очереди задач серверного режима: Postgres-очередь и сервис жизненного цикла."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService


class ServerJobsProvider(Provider):
    scope = Scope.APP

    @provide
    def get_job_queue(self, sessions: SessionProvider) -> IJobQueue:
        return PostgresJobQueue(sessions)

    @provide
    def get_job_queue_service(self, queue: IJobQueue) -> JobQueueService:
        return JobQueueService(queue, lease_s=settings.jobs.lease_s, timeout_grace_s=settings.jobs.timeout_grace_s)
