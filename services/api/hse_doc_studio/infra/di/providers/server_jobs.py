"""Провайдер очереди задач серверного режима: Postgres-очередь, сервис жизненного цикла, хранилище входов и выходов."""

from __future__ import annotations

from pathlib import Path
from typing import NewType

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.runners import (
    JOB_TOKEN_KEY_PURPOSE,
    IRegistrationTokenRepository,
    IRunnerRepository,
    JobTokenSigner,
)
from hse_doc_studio.core.jobs.storage import IJobBlobStore, IJobLogSink, IJobOutputIngest
from hse_doc_studio.core.storage import IBlobStore, IObjectStore
from hse_doc_studio.core.storage.ingest import OutputLimits
from hse_doc_studio.core.storage.manifest import ILiveBlobSource
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.repositories.runners import SqlRegistrationTokenRepository, SqlRunnerRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.jobs.live_blobs import QueueLiveBlobs
from hse_doc_studio.infra.jobs.object_storage import AnnouncedJobOutputIngest, ObjectJobBlobStore
from hse_doc_studio.infra.jobs.storage_fs import FsJobLogSink
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.storage.job_output_ingest import ObjectJobOutputIngest
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

JobStorageRoot = NewType("JobStorageRoot", Path)


class ServerJobsProvider(Provider):
    scope = Scope.APP

    @provide
    def get_job_queue(self, sessions: SessionProvider) -> IJobQueue:
        return PostgresJobQueue(sessions)

    @provide
    def get_job_queue_service(self, queue: IJobQueue) -> JobQueueService:
        return JobQueueService(queue, lease_s=settings.jobs.lease_s, timeout_grace_s=settings.jobs.timeout_grace_s)

    @provide
    def get_runner_repository(self, sessions: SessionProvider) -> IRunnerRepository:
        return SqlRunnerRepository(sessions)

    @provide
    def get_registration_token_repository(self, sessions: SessionProvider) -> IRegistrationTokenRepository:
        return SqlRegistrationTokenRepository(sessions)

    @provide
    def get_runner_registry(
        self, runners: IRunnerRepository, tokens: IRegistrationTokenRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> RunnerRegistry:
        return RunnerRegistry(runners, tokens, audit, uow)

    @provide
    def get_job_token_signer(self, key_store: KeyFileStore) -> JobTokenSigner:
        """Ключи подписи производные от связки секретов: ротация ключа охватывает и токены задач."""
        return JobTokenSigner(key_store.ensure_primary().derive_all(JOB_TOKEN_KEY_PURPOSE))

    @provide
    def get_job_wakeup(self) -> JobWakeup:
        return JobWakeup()

    @provide
    def get_runner_job_service(
        self,
        queue: IJobQueue,
        queue_service: JobQueueService,
        runners: IRunnerRepository,
        signer: JobTokenSigner,
        wakeup: JobWakeup,
        quotas: QuotaService,
    ) -> RunnerJobService:
        return RunnerJobService(
            queue,
            queue_service,
            runners,
            signer,
            wakeup,
            lease_s=settings.jobs.lease_s,
            timeout_grace_s=settings.jobs.timeout_grace_s,
            quota_source=quotas.current,
        )

    @provide
    def get_job_storage_root(self) -> JobStorageRoot:
        """Каталог лога задач: блобы и выходы живут в объектном хранилище."""
        return JobStorageRoot(settings.jobs.storage_dir or settings.data_dir.expanduser() / "jobs")

    @provide
    def get_job_blob_store(self, blobs: IBlobStore) -> IJobBlobStore:
        return ObjectJobBlobStore(blobs)

    @provide
    def get_job_output_ingest(self, queue: IJobQueue, store: IObjectStore) -> IJobOutputIngest:
        limits = OutputLimits(max_file_bytes=settings.jobs.max_artifact_bytes)
        return AnnouncedJobOutputIngest(queue, store, ObjectJobOutputIngest(store, limits=limits))

    @provide(override=True)
    def get_live_blobs(self, queue: IJobQueue) -> ILiveBlobSource:
        """Блобы манифестов queued и running задач не собираются мусором, как бы давно на них ни ссылались."""
        return QueueLiveBlobs(queue)

    @provide
    def get_job_log_sink(self, root: JobStorageRoot) -> IJobLogSink:
        return FsJobLogSink(root, max_bytes=settings.jobs.max_log_bytes)

    @provide
    def get_runner_job_io_service(
        self,
        queue: IJobQueue,
        queue_service: JobQueueService,
        runners: IRunnerRepository,
        signer: JobTokenSigner,
        blobs: IJobBlobStore,
        outputs: IJobOutputIngest,
        logs: IJobLogSink,
    ) -> RunnerJobIoService:
        return RunnerJobIoService(queue, queue_service, runners, signer, blobs, outputs, logs)
