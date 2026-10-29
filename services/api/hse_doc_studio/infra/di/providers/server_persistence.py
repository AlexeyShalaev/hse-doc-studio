"""Провайдер хранения серверного режима (Postgres).

Модуль тянет sqlalchemy, поэтому подключается лениво, только из ``create_container(server)``.
Репозитории регистрируются здесь по мере готовности срезов и перекрывают локальные через
``override=True``; пока их нет, серверный контейнер берёт остальное у ``LocalPersistenceProvider``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hse_doc_studio.api.config import ServerConfig, settings
from hse_doc_studio.core.access.checker import IProjectAccessChecker
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.git_sync.fetch_schedule import FetchBook
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, IGitRemoteRegistry
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.jobs.artifacts import IArtifactStore
from hse_doc_studio.core.projects.lifecycle import ServerProjectStorage
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.projects.usage import (
    IProjectQuota,
    IProjectUsageMeasurer,
    IProjectUsageStore,
    QuotaPolicy,
)
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.repositories import (
    ICompileRepository,
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.storage import IBlobStore, IObjectStore
from hse_doc_studio.core.storage.manifest import IBlobRegistry, IBlobUploader, ILiveBlobSource, ManifestLimits
from hse_doc_studio.core.submission_archive import ISubmissionArchive, ISubmissionAudit
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.infra.db.engine import create_engine, create_sessionmaker
from hse_doc_studio.infra.db.repositories.blobs import PostgresBlobRegistry
from hse_doc_studio.infra.db.repositories.compile import PostgresCompileRepository
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository, RequestAclCache
from hse_doc_studio.infra.db.repositories.project_usage import PostgresProjectUsageStore
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.repositories.submission import PostgresPackSubmissionRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.infra.identity.project_access import ServerProjectAccessChecker
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore
from hse_doc_studio.infra.jobs.s3_artifact_store import S3ArtifactStore
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer
from hse_doc_studio.infra.projects.acl_flags import AclFlagsCache
from hse_doc_studio.infra.projects.catalog_index import CatalogProjectIndex
from hse_doc_studio.infra.projects.catalog_sync import (
    MirroringProjectRepository,
    ProjectCatalogMirror,
    ProjectCatalogReconciler,
)
from hse_doc_studio.infra.projects.orphan_gc import OrphanGc
from hse_doc_studio.infra.projects.purge import ProjectPurger
from hse_doc_studio.infra.projects.usage_meter import ProjectQuotaService, ProjectUsageSweeper, VolumeUsageMeasurer
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.secrets.server_keys import server_key_store
from hse_doc_studio.infra.storage.blob_uploader import ManifestBlobUploader
from hse_doc_studio.infra.storage.blobs import ObjectBlobStore
from hse_doc_studio.infra.storage.factory import create_object_store
from hse_doc_studio.infra.storage.live import NoLiveBlobs
from hse_doc_studio.infra.submission.archive import AuditSubmissionDownloads, ObjectSubmissionArchive
from hse_doc_studio.use_cases.git_sync.clone_project import GetCloneDefaultsUC
from hse_doc_studio.use_cases.projects.create_project import CreateProjectUC
from hse_doc_studio.use_cases.projects.get_project_suggestions import GetProjectSuggestionsUC
from hse_doc_studio.use_cases.projects.list_projects import ListProjectsUC
from hse_doc_studio.use_cases.projects.unregister_project import UnregisterProjectUC
from hse_doc_studio.use_cases.projects.update_team_set import UpdateTeamSetUC
from hse_doc_studio.use_cases.storage.gc_blobs import GcBlobsUC
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService


class ServerPersistenceProvider(Provider):
    scope = Scope.APP

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        """``engine`` подставляют тесты: тогда его жизнью владеет вызывающий, контейнер его не закрывает."""
        super().__init__()
        self._engine = engine

    @provide
    def get_server_config(self) -> ServerConfig:
        return ServerConfig.from_settings(settings)

    @provide
    async def get_engine(self) -> AsyncIterator[AsyncEngine]:
        if self._engine is not None:
            yield self._engine
            return
        engine = create_engine(settings.db)
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide
    def get_sessionmaker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return create_sessionmaker(engine)

    @provide
    def get_session_provider(self, sessionmaker: async_sessionmaker[AsyncSession]) -> SessionProvider:
        return SessionProvider(sessionmaker)

    @provide
    def get_unit_of_work(self, sessions: SessionProvider) -> IUnitOfWork:
        return SqlUnitOfWork(sessions)

    @provide(override=True)
    def get_git_key_store(self) -> KeyFileStore:
        """В server ключ только из окружения: без него контейнер не создаётся."""
        return server_key_store(settings)

    @provide
    def get_project_volume(self, server_config: ServerConfig) -> IProjectVolume:
        return LocalDiskProjectVolume(server_config.projects_root)

    @provide
    def get_object_store(self, server_config: ServerConfig) -> IObjectStore:
        return create_object_store(server_config.s3, settings.data_dir.expanduser())

    @provide(override=True)
    def get_artifact_store(self, store: IObjectStore) -> IArtifactStore:
        return S3ArtifactStore(store, LocalDiskArtifactStore())

    @provide
    def get_blob_store(self, store: IObjectStore) -> IBlobStore:
        return ObjectBlobStore(store)

    @provide
    def get_blob_registry(self, sessions: SessionProvider) -> IBlobRegistry:
        return PostgresBlobRegistry(sessions)

    @provide
    def get_manifest_limits(self, server_config: ServerConfig) -> ManifestLimits:
        return ManifestLimits(
            max_file_bytes=server_config.manifest_max_file_bytes, max_job_bytes=server_config.manifest_max_job_bytes
        )

    @provide
    def get_blob_uploader(self, volume: IProjectVolume, registry: IBlobRegistry, blobs: IBlobStore) -> IBlobUploader:
        return ManifestBlobUploader(volume, registry, blobs)

    @provide
    def get_live_blobs(self) -> ILiveBlobSource:
        """Пока в системе нет очереди задач, незавершённых задач с блобами тоже нет; срез очереди подменит источник."""
        return NoLiveBlobs()

    @provide
    def get_gc_blobs_uc(
        self,
        registry: IBlobRegistry,
        blobs: IBlobStore,
        objects: IObjectStore,
        live: ILiveBlobSource,
        server_config: ServerConfig,
    ) -> GcBlobsUC:
        return GcBlobsUC(registry, blobs, objects, live, min_age=timedelta(days=server_config.blob_gc_min_age_days))

    @provide
    def get_project_catalog_mirror(self, sessions: SessionProvider) -> ProjectCatalogMirror:
        return ProjectCatalogMirror(sessions)

    @provide
    def get_acl_flags(self) -> AclFlagsCache:
        return AclFlagsCache()

    @provide
    def get_mirroring_project_repo(
        self, volume: IProjectVolume, mirror: ProjectCatalogMirror, flags: AclFlagsCache
    ) -> MirroringProjectRepository:
        return MirroringProjectRepository(JsonProjectRepository(), volume, mirror, flags)

    @provide(override=True)
    def get_project_repo(self, repo: MirroringProjectRepository) -> IProjectRepository:
        """project.json остаётся источником содержимого; копия name/kind/lang уходит в каталог на каждый save,
        а поля, от которых зависят права, читаются и пишутся значением из БД."""
        return repo

    @provide
    def get_postgres_project_acl(self, sessions: SessionProvider, flags: AclFlagsCache) -> PostgresProjectAclRepository:
        return PostgresProjectAclRepository(sessions, flags)

    @provide(scope=Scope.REQUEST)
    def get_project_acl(self, inner: PostgresProjectAclRepository) -> IProjectAclRepository:
        return RequestAclCache(inner)

    @provide(override=True)
    def get_project_access_checker(self, acl: PostgresProjectAclRepository) -> IProjectAccessChecker:
        return ServerProjectAccessChecker(acl)

    @provide(override=True)
    def get_list_projects_uc(
        self, project_repo: IProjectRepository, locator: IProjectLocator, acl: PostgresProjectAclRepository
    ) -> ListProjectsUC:
        return ListProjectsUC(project_repo=project_repo, locator=locator, memberships=acl)

    @provide(override=True)
    def get_project_suggestions_uc(self, list_projects: ListProjectsUC) -> GetProjectSuggestionsUC:
        return GetProjectSuggestionsUC(
            list_projects=list_projects,
            default_projects_dir=settings.data_dir.expanduser() / "projects",
            with_folders=False,
        )

    @provide(override=True)
    def get_project_locator(
        self, sessions: SessionProvider, volume: IProjectVolume, projects: IProjectRepository
    ) -> IProjectLocator:
        return PostgresProjectLocator(sessions, volume, projects)

    @provide(override=True)
    def get_project_index_repo(self, locator: IProjectLocator) -> IProjectIndexRepository:
        """Локальный projects.json в серверном режиме пуст: проект по id находит каталог в БД."""
        return CatalogProjectIndex(locator)

    @provide(override=True)
    def get_compile_repo(
        self, sessions: SessionProvider, volume: IProjectVolume, server_config: ServerConfig
    ) -> ICompileRepository:
        return PostgresCompileRepository(
            sessions,
            volume,
            keep_per_document=server_config.compile_records_per_document,
            log_limit_bytes=server_config.compile_log_limit_bytes,
        )

    @provide(override=True)
    def get_pack_submission_repo(self, sessions: SessionProvider, volume: IProjectVolume) -> IPackSubmissionRepository:
        return PostgresPackSubmissionRepository(sessions, volume)

    @provide(override=True)
    def get_submission_archive(self, store: IObjectStore) -> ISubmissionArchive:
        return ObjectSubmissionArchive(store)

    @provide(override=True)
    def get_submission_audit(self, audit: IAuditLog) -> ISubmissionAudit:
        return AuditSubmissionDownloads(audit)

    @provide(override=True)
    def get_git_clone_defaults_uc(self, locator: IProjectLocator, volume: IProjectVolume) -> GetCloneDefaultsUC:
        return GetCloneDefaultsUC(volume.root, locator, uuid_names=True)

    @provide
    def get_project_catalog_reconciler(
        self, sessions: SessionProvider, volume: IProjectVolume, projects: MirroringProjectRepository
    ) -> ProjectCatalogReconciler:
        return ProjectCatalogReconciler(sessions, volume, projects)

    @provide
    def get_project_purger(
        self, sessions: SessionProvider, volume: IProjectVolume, server_config: ServerConfig
    ) -> ProjectPurger:
        return ProjectPurger(sessions, volume, timedelta(days=server_config.project_retention_days))

    @provide
    def get_project_usage_store(self, sessions: SessionProvider) -> IProjectUsageStore:
        return PostgresProjectUsageStore(sessions)

    @provide
    def get_project_usage_measurer(self, volume: IProjectVolume, store: IObjectStore) -> IProjectUsageMeasurer:
        return VolumeUsageMeasurer(volume, store)

    @provide(override=True)
    def get_project_quota(
        self, usage: IProjectUsageStore, measurer: IProjectUsageMeasurer, server_config: ServerConfig
    ) -> IProjectQuota:
        policy = QuotaPolicy(server_config.project_quota_bytes, server_config.project_quota_warn_percent / 100)
        return ProjectQuotaService(usage, measurer, policy)

    @provide
    def get_project_usage_sweeper(
        self, usage: IProjectUsageStore, measurer: IProjectUsageMeasurer, server_config: ServerConfig
    ) -> ProjectUsageSweeper:
        return ProjectUsageSweeper(
            usage,
            measurer,
            max_age=timedelta(seconds=server_config.project_usage_interval_s),
            batch_size=server_config.project_usage_batch,
        )

    @provide
    def get_orphan_gc(
        self, sessions: SessionProvider, volume: IProjectVolume, store: IObjectStore, server_config: ServerConfig
    ) -> OrphanGc:
        return OrphanGc(sessions, volume, store, timedelta(hours=server_config.orphan_gc_min_age_hours))

    @provide
    def get_server_project_storage(
        self, volume: IProjectVolume, locator: IProjectLocator, uow: IUnitOfWork
    ) -> ServerProjectStorage:
        return ServerProjectStorage(volume=volume, locator=locator, uow=uow)

    @provide(scope=Scope.REQUEST, override=True)
    def get_create_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        template_renderer: TemplateRenderer,
        vcs_service: IVcsService,
        base_service: TemplateBaseService,
        storage: ServerProjectStorage,
    ) -> CreateProjectUC:
        return CreateProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            template_service=template_service,
            template_renderer=template_renderer,
            vcs_service=vcs_service,
            base_service=base_service,
            server_storage=storage,
        )

    @provide(scope=Scope.REQUEST, override=True)
    def get_update_team_set_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_renderer: TemplateRenderer,
        vcs_service: IVcsService,
        base_service: TemplateBaseService,
        acl: IProjectAclRepository,
    ) -> UpdateTeamSetUC:
        return UpdateTeamSetUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            template_renderer=template_renderer,
            vcs_service=vcs_service,
            base_service=base_service,
            acl=acl,
        )

    @provide(scope=Scope.REQUEST, override=True)
    def get_unregister_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        git_operations: IGitOperationRegistry,
        git_remotes: IGitRemoteRegistry,
        book: FetchBook,
        storage: ServerProjectStorage,
    ) -> UnregisterProjectUC:
        return UnregisterProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            git_operations=git_operations,
            git_remotes=git_remotes,
            fetch_book=book,
            server_storage=storage,
        )
