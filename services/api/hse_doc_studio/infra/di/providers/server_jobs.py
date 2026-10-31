"""Провайдер очереди задач серверного режима: Postgres-очередь, сервис жизненного цикла, хранилище входов и выходов."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import NewType
from uuid import UUID

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.links import IBuildPayerResolver
from hse_doc_studio.core.compile.wait import ICompileWaitReader
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.identity.instance_settings import InstanceEnvOverrides, effective_build_settings
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository, IUserRepository
from hse_doc_studio.core.jobs.applier import IJobApplyLedger, IJobHooksFactory, IJobResultApplier
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.quotas import IProjectOrgReader, IQuotaOverrideRepository
from hse_doc_studio.core.jobs.routing import (
    IJobRouter,
    IPersonalRunnerLoad,
    IPersonalRunnerSettings,
    IProjectRoutePolicy,
)
from hse_doc_studio.core.jobs.runners import (
    JOB_TOKEN_KEY_PURPOSE,
    IRegistrationTokenRepository,
    IRunnerRepository,
    JobTokenSigner,
)
from hse_doc_studio.core.jobs.storage import IJobBlobStore, IJobLogSink, IJobOutputIngest
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    ICompileRepository,
    IProjectRepository,
    ISettingsRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.storage import IBlobStore, IObjectStore
from hse_doc_studio.core.storage.ingest import OutputLimits
from hse_doc_studio.core.storage.manifest import IBlobRegistry, IBlobUploader, ILiveBlobSource, ManifestLimits
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.infra.db.repositories.job_quotas import SqlProjectOrgReader, SqlQuotaOverrideRepository
from hse_doc_studio.infra.db.repositories.jobs import PostgresJobQueue
from hse_doc_studio.infra.db.repositories.jobs_applied import SqlJobApplyLedger
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository
from hse_doc_studio.infra.db.repositories.project_route_policy import SqlProjectRoutePolicyRepository
from hse_doc_studio.infra.db.repositories.runner_pairings import SqlRunnerPairingRepository
from hse_doc_studio.infra.db.repositories.runners import SqlRegistrationTokenRepository, SqlRunnerRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.jobs.compile_wait import QueueCompileWaitReader
from hse_doc_studio.infra.jobs.live_blobs import QueueLiveBlobs
from hse_doc_studio.infra.jobs.object_storage import AnnouncedJobOutputIngest, ObjectJobBlobStore
from hse_doc_studio.infra.jobs.queue_dispatcher import QueueJobDispatcher
from hse_doc_studio.infra.jobs.result_applier import VolumeJobResultApplier
from hse_doc_studio.infra.jobs.retention import JobRetention
from hse_doc_studio.infra.jobs.storage_fs import FsJobLogSink
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.storage.job_output_ingest import ObjectJobOutputIngest
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.compile.compile_hooks_factory import CompileJobHooksFactory
from hse_doc_studio.use_cases.jobs.pairing import RunnerPairingService
from hse_doc_studio.use_cases.jobs.personal_settings import InstancePersonalRunnerSettings
from hse_doc_studio.use_cases.jobs.project_build_runners import ProjectBuildRunnersService
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.routing import JobRouter
from hse_doc_studio.use_cases.jobs.runner_io import RunnerJobIoService
from hse_doc_studio.use_cases.jobs.runner_jobs import RunnerJobService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.jobs.terminal import JobTerminalBroadcaster
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup

JobStorageRoot = NewType("JobStorageRoot", Path)


class ServerJobsProvider(Provider):
    scope = Scope.APP

    @provide
    def get_postgres_job_queue(self, sessions: SessionProvider) -> PostgresJobQueue:
        return PostgresJobQueue(sessions)

    @provide
    def get_job_queue(self, queue: PostgresJobQueue) -> IJobQueue:
        return queue

    @provide
    def get_personal_runner_load(self, queue: PostgresJobQueue) -> IPersonalRunnerLoad:
        return queue

    @provide
    def get_job_terminal_broadcaster(self) -> JobTerminalBroadcaster:
        return JobTerminalBroadcaster()

    @provide
    def get_job_queue_service(
        self, queue: IJobQueue, wakeup: JobWakeup, terminal: JobTerminalBroadcaster
    ) -> JobQueueService:
        return JobQueueService(
            queue,
            lease_s=settings.jobs.lease_s,
            timeout_grace_s=settings.jobs.timeout_grace_s,
            wakeup=wakeup,
            terminal=terminal,
        )

    @provide
    def get_personal_runner_settings(
        self, repo: IInstanceSettingsRepository, env: InstanceEnvOverrides
    ) -> InstancePersonalRunnerSettings:
        return InstancePersonalRunnerSettings(repo, env)

    @provide
    def get_personal_runner_settings_port(self, value: InstancePersonalRunnerSettings) -> IPersonalRunnerSettings:
        return value

    @provide
    def get_project_route_policy(self, sessions: SessionProvider) -> IProjectRoutePolicy:
        return SqlProjectRoutePolicyRepository(sessions)

    @provide
    def get_job_router(
        self,
        personal: IPersonalRunnerSettings,
        projects: IProjectRoutePolicy,
        runners: IRunnerRepository,
        load: IPersonalRunnerLoad,
    ) -> JobRouter:
        return JobRouter(personal, projects, runners, load)

    @provide
    def get_job_router_port(self, router: JobRouter) -> IJobRouter:
        return router

    @provide(override=True)
    def get_compile_wait_reader(
        self,
        queue: IJobQueue,
        runners: IRunnerRepository,
        projects: IProjectRoutePolicy,
        personal: IPersonalRunnerSettings,
    ) -> ICompileWaitReader:
        return QueueCompileWaitReader(queue, runners, projects=projects, personal=personal)

    @provide
    def get_runner_repository(self, sessions: SessionProvider) -> IRunnerRepository:
        return SqlRunnerRepository(sessions)

    @provide
    def get_registration_token_repository(self, sessions: SessionProvider) -> IRegistrationTokenRepository:
        return SqlRegistrationTokenRepository(sessions)

    @provide
    def get_quota_override_repository(self, sessions: SessionProvider) -> IQuotaOverrideRepository:
        return SqlQuotaOverrideRepository(sessions)

    @provide
    def get_project_org_reader(self, sessions: SessionProvider) -> IProjectOrgReader:
        return SqlProjectOrgReader(sessions)

    @provide
    def get_runner_registry(  # noqa: PLR0913
        self,
        runners: IRunnerRepository,
        tokens: IRegistrationTokenRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        personal: IPersonalRunnerSettings,
        users: IUserRepository,
        queue_service: JobQueueService,
        queue: IJobQueue,
    ) -> RunnerRegistry:
        return RunnerRegistry(
            runners, tokens, audit, uow, personal=personal, users=users, queue=queue_service, jobs=queue
        )

    @provide
    def get_project_build_runners_service(  # noqa: PLR0913
        self,
        projects: IProjectRoutePolicy,
        runners: IRunnerRepository,
        personal: IPersonalRunnerSettings,
        audit: IAuditLog,
        uow: IUnitOfWork,
        queue: JobQueueService,
    ) -> ProjectBuildRunnersService:
        return ProjectBuildRunnersService(projects, runners, personal, audit, uow, queue)

    @provide
    def get_runner_pairing_service(
        self,
        sessions: SessionProvider,
        registry: RunnerRegistry,
        cipher: ISecretCipher,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> RunnerPairingService:
        return RunnerPairingService(SqlRunnerPairingRepository(sessions), registry, cipher, audit, uow)

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
        personal: IPersonalRunnerSettings,
        users: IUserRepository,
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
            personal_settings=personal,
            users=users,
        )

    @provide
    def get_job_storage_root(self) -> JobStorageRoot:
        """Каталог лога задач: блобы и выходы живут в объектном хранилище."""
        return JobStorageRoot(settings.jobs.storage_dir or settings.data_dir.expanduser() / "jobs")

    @provide
    def get_job_retention(self, sessions: SessionProvider, store: IObjectStore, root: JobStorageRoot) -> JobRetention:
        days = settings.server.job_retention_days
        return JobRetention(
            sessions,
            store,
            root,
            output_min_age=timedelta(hours=settings.server.job_output_min_age_hours),
            retention=timedelta(days=days) if days > 0 else None,
        )

    @provide
    def get_job_blob_store(self, blobs: IBlobStore, registry: IBlobRegistry) -> IJobBlobStore:
        return ObjectJobBlobStore(blobs, registry)

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

    @provide
    def get_job_apply_ledger(self, sessions: SessionProvider) -> IJobApplyLedger:
        return SqlJobApplyLedger(sessions)

    @provide
    def get_job_result_applier(
        self, volume: IProjectVolume, store: IObjectStore, artifacts: IArtifactStore, outputs: IJobOutputIngest
    ) -> IJobResultApplier:
        return VolumeJobResultApplier(volume, store, artifacts, outputs)

    @provide
    def get_job_hooks_factory(  # noqa: PLR0913
        self,
        compile_repo: ICompileRepository,
        project_repo: IProjectRepository,
        changelog_repo: IChangeLogRepository,
        template_repo: ITemplateRepository,
        vcs_service: IVcsService,
        vcs_locks: IVcsFolderLocks,
        artifacts: IArtifactStore,
    ) -> IJobHooksFactory:
        return CompileJobHooksFactory(
            compile_repo, project_repo, changelog_repo, template_repo, vcs_service, vcs_locks, artifacts
        )

    @provide(override=True)
    def get_job_dispatcher(  # noqa: PLR0913
        self,
        queue: IJobQueue,
        uploader: IBlobUploader,
        runners: IRunnerRepository,
        limits: ManifestLimits,
        acl: PostgresProjectAclRepository,
        applier: IJobResultApplier,
        ledger: IJobApplyLedger,
        hooks_factory: IJobHooksFactory,
        volume: IProjectVolume,
        settings_repo: ISettingsRepository,
        quotas: QuotaService,
        project_orgs: IProjectOrgReader,
        instance_settings: IInstanceSettingsRepository,
        env: InstanceEnvOverrides,
        wakeup: JobWakeup,
        router: IJobRouter,
        payer: IBuildPayerResolver,
    ) -> IJobDispatcher:
        async def role_of(actor: Actor, project_id: UUID) -> Role | None:
            project_acl = await acl.load_for(actor, project_id)
            grant = project_acl.grant_for(actor) if project_acl is not None else None
            return grant.role if grant is not None else None

        async def build_timeout_s() -> float | None:
            return effective_build_settings(await instance_settings.get_all(), env).timeout_s

        return QueueJobDispatcher(
            queue,
            uploader,
            runners,
            limits=limits,
            role_source=role_of,
            applier=applier,
            ledger=ledger,
            hooks_factory=hooks_factory,
            volume=volume,
            settings_repo=settings_repo,
            quotas=quotas,
            project_orgs=project_orgs,
            build_timeout_source=build_timeout_s,
            wakeup=wakeup,
            router=router,
            # links: гость по ссылке собирает в квоту создателя ссылки (S7).
            payer=payer.payer_for,
        )
