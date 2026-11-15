"""Студия шаблонов на сервере: пространства и право «Автор шаблонов» в Postgres, включение раздела у админа, аудит,
сборки предпросмотра через очередь и раннеры установки."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.links import IBuildPayerResolver
from hse_doc_studio.core.events import IJobLogStream
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitTransport
from hse_doc_studio.core.identity.instance_settings import InstanceEnvOverrides, effective_build_settings
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.jobs.applier import IJobApplyLedger
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.quotas import IProjectOrgReader
from hse_doc_studio.core.jobs.routing import IJobRouter
from hse_doc_studio.core.jobs.runners import IRunnerRepository
from hse_doc_studio.core.jobs.storage import IJobLogReader, IJobOutputIngest
from hse_doc_studio.core.pack_studio.protocols import (
    IPackStudioGrantRepository,
    IPackStudioSectionStore,
    IPackWorkspaceFiles,
    IPackWorkspaceGit,
    IPackWorkspaceRepository,
    IPreviewDispatcher,
)
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.quotas.protocols import IQuotaGate
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.storage import IBlobStore, IObjectStore
from hse_doc_studio.core.storage.manifest import IBlobRegistry, ManifestLimits
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.pack_studio import (
    InstanceSectionStore,
    PostgresPackStudioGrantRepository,
    PostgresPackWorkspaceRepository,
)
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.di.providers.pack_studio import PackStudioProvider, previews_root
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore
from hse_doc_studio.infra.jobs.queue_dispatcher import QueueJobDispatcher
from hse_doc_studio.infra.jobs.result_applier import VolumeJobResultApplier
from hse_doc_studio.infra.pack_studio.preview_dispatch import NoHashCacheRegistry, PreviewJobDispatcher
from hse_doc_studio.infra.pack_studio.preview_store import WORK_DIR
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.storage.blob_uploader import ManifestBlobUploader
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.jobs.wakeup import JobWakeup
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess
from hse_doc_studio.use_cases.pack_studio.admin import PackStudioAdminUC
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService, WorkspaceTasks


class ServerPackStudioProvider(Provider):
    scope = Scope.APP

    @provide(override=True)
    def get_workspace_repo(self, sessions: SessionProvider) -> IPackWorkspaceRepository:
        return PostgresPackWorkspaceRepository(sessions)

    @provide
    def get_grant_repo(self, sessions: SessionProvider) -> IPackStudioGrantRepository:
        return PostgresPackStudioGrantRepository(sessions)

    @provide(override=True)
    def get_section_store(self, instance: IInstanceSettingsRepository) -> IPackStudioSectionStore:
        return InstanceSectionStore(instance)

    @provide(override=True)
    def get_access(self, store: IPackStudioSectionStore, grants: IPackStudioGrantRepository) -> PackStudioAccess:
        cfg = settings.pack_studio
        return PackStudioAccess(store, grants, forced=cfg.enabled, standalone=cfg.standalone)

    @provide(override=True)
    def get_workspace_service(  # noqa: PLR0913 — порты сценария
        self,
        repo: IPackWorkspaceRepository,
        files: IPackWorkspaceFiles,
        git: IPackWorkspaceGit,
        transport: IGitTransport,
        credentials: IGitCredentialRepository,
        policy: GitSyncPolicy,
        paths: PathMapping,
        tasks: WorkspaceTasks,
        audit: IAuditLog,
    ) -> PackWorkspaceService:
        return PackStudioProvider.build_service(
            repo, files, git, transport, credentials, policy, paths, tasks, audit=audit
        )

    @provide(override=True)
    def get_preview_dispatcher(  # noqa: PLR0913 — те же порты, что у диспетчера сборок проектов
        self,
        queue: IJobQueue,
        runners: IRunnerRepository,
        registry: IBlobRegistry,
        blobs: IBlobStore,
        objects: IObjectStore,
        outputs: IJobOutputIngest,
        limits: ManifestLimits,
        ledger: IJobApplyLedger,
        settings_repo: ISettingsRepository,
        quotas: QuotaService,
        project_orgs: IProjectOrgReader,
        instance_settings: IInstanceSettingsRepository,
        env: InstanceEnvOverrides,
        wakeup: JobWakeup,
        router: IJobRouter,
        payer: IBuildPayerResolver,
        quota_gate: IQuotaGate,
        log_reader: IJobLogReader,
        log_stream: IJobLogStream,
    ) -> IPreviewDispatcher:
        """Та же очередь, раннеры, квота сборок и маршруты, что у сборок проектов; вход и выходы задачи живут на
        томе предпросмотра (`previews/work/<id задачи>`), PDF не уходит в архив проекта, восстановления нет."""
        volume = LocalDiskProjectVolume(previews_root() / WORK_DIR)

        async def build_timeout_s() -> float | None:
            return effective_build_settings(await instance_settings.get_all(), env).timeout_s

        dispatcher = QueueJobDispatcher(
            queue,
            ManifestBlobUploader(volume, NoHashCacheRegistry(registry), blobs),
            runners,
            limits=limits,
            applier=VolumeJobResultApplier(volume, objects, LocalDiskArtifactStore(), outputs),
            ledger=ledger,
            settings_repo=settings_repo,
            quotas=quotas,
            project_orgs=project_orgs,
            build_timeout_source=build_timeout_s,
            wakeup=wakeup,
            router=router,
            payer=payer.payer_for,
            quota_gate=quota_gate,
            log_reader=log_reader,
            log_stream=log_stream,
        )
        return PreviewJobDispatcher(dispatcher)

    @provide
    def get_admin_uc(
        self,
        access: PackStudioAccess,
        store: IPackStudioSectionStore,
        grants: IPackStudioGrantRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> PackStudioAdminUC:
        return PackStudioAdminUC(access, store, grants, audit, uow)
