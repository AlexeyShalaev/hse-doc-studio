"""Студия шаблонов (docs/design/template-studio.md, срез T5): локальные провайдеры и серверные поверх них.

Локально пространства лежат в `data_dir/pack-studio/workspaces.json`, выбор «раздел включён» в `config.json`, права
раздела нет (человек один). Сервер подменяет хранилища на Postgres, включение на настройки установки и добавляет право
«Автор шаблонов» и журнал аудита.
"""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    ICredentialAccess,
    IGitCredentialRepository,
    IGitRemoteRunner,
    IGitTransport,
)
from hse_doc_studio.core.identity.commit_identity import noreply_domain
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.pack_studio.official import OfficialRepo
from hse_doc_studio.core.pack_studio.official import official_repo as make_official_repo
from hse_doc_studio.core.pack_studio.protocols import (
    IPackChecker,
    IPackHosting,
    IPackPreviewRenderer,
    IPackStudioSectionStore,
    IPackVersions,
    IPackWorkspaceFiles,
    IPackWorkspaceGit,
    IPackWorkspaceRepository,
    IPreviewDispatcher,
    IPreviewStore,
    IServiceAccessRepository,
    WorkspaceLimits,
)
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.vcs.protocols import ICommitAuthorProvider
from hse_doc_studio.infra.pack_studio.hosting import HttpPackHosting
from hse_doc_studio.infra.pack_studio.inspector import PackInspector
from hse_doc_studio.infra.pack_studio.local_store import JsonPackWorkspaceRepository, LocalSectionStore
from hse_doc_studio.infra.pack_studio.places import PackPlacesEditor
from hse_doc_studio.infra.pack_studio.plumbing import PackGitPlumbing
from hse_doc_studio.infra.pack_studio.preview_dispatch import PreviewJobDispatcher
from hse_doc_studio.infra.pack_studio.preview_renderer import PackPreviewRenderer, PreviewRenderLimits
from hse_doc_studio.infra.pack_studio.preview_store import FsPreviewStore
from hse_doc_studio.infra.pack_studio.preview_worker import StageLimits
from hse_doc_studio.infra.pack_studio.version_wizard import PackVersionWizard
from hse_doc_studio.infra.pack_studio.workspace_check import WorkspacePackChecker
from hse_doc_studio.infra.pack_studio.workspace_files import LocalPackWorkspaceFiles
from hse_doc_studio.infra.pack_studio.workspace_git import PackWorkspaceGit, workspace_dirs
from hse_doc_studio.infra.pack_studio.yaml_edits import PackYamlEditor
from hse_doc_studio.use_cases.git_sync.provider_resolver import ProviderResolver
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.git import PackGitService
from hse_doc_studio.use_cases.pack_studio.insight import PackInsightService
from hse_doc_studio.use_cases.pack_studio.official import OfficialPacks
from hse_doc_studio.use_cases.pack_studio.places import PackPlacesService
from hse_doc_studio.use_cases.pack_studio.preview import PackPreviewService, PreviewLimits
from hse_doc_studio.use_cases.pack_studio.versions import PackVersionService
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService, WorkspaceTasks


def workspace_limits() -> WorkspaceLimits:
    cfg = settings.pack_studio
    return WorkspaceLimits(
        max_file_bytes=cfg.max_file_bytes,
        max_read_bytes=cfg.max_read_bytes,
        max_clone_bytes=cfg.max_clone_bytes,
        max_tree_bytes=cfg.max_tree_bytes,
        max_tree_files=cfg.max_tree_files,
    )


def official_repo() -> OfficialRepo | None:
    cfg = settings.pack_studio
    return make_official_repo(
        cfg.official_repo_url,
        packs_path=cfg.official_packs_path,
        base_branch=cfg.official_base_branch,
        license=cfg.official_license,
    )


def previews_root() -> Path:
    return settings.data_dir / "pack-studio" / "previews"


def preview_store() -> FsPreviewStore:
    cfg = settings.pack_studio
    return FsPreviewStore(
        previews_root(), max_cache_entries=cfg.preview_cache_entries, max_age_s=cfg.preview_keep_hours * 3600
    )


class PackStudioProvider(Provider):
    scope = Scope.APP

    @provide
    def get_workspace_tasks(self) -> WorkspaceTasks:
        # Общий на процесс: одна фоновая операция на пространство, сколько бы запросов ни пришло.
        return WorkspaceTasks()

    @provide
    def get_workspace_repo(self) -> IPackWorkspaceRepository:
        return JsonPackWorkspaceRepository(settings.data_dir)

    @provide
    def get_section_store(self, repo: ISettingsRepository) -> IPackStudioSectionStore:
        return LocalSectionStore(repo)

    @provide
    def get_access(self, store: IPackStudioSectionStore) -> PackStudioAccess:
        cfg = settings.pack_studio
        return PackStudioAccess(store, None, forced=cfg.enabled, standalone=cfg.standalone)

    @provide
    def get_workspace_files(self) -> IPackWorkspaceFiles:
        return LocalPackWorkspaceFiles()

    @provide
    def get_git_plumbing(
        self, runner: IGitRemoteRunner, transport: IGitTransport, access: ICredentialAccess
    ) -> PackGitPlumbing:
        # Локально служебных доступов нет: те же запускатель, транспорт и доступ, что у синхронизации проектов.
        return PackGitPlumbing(runner=runner, transport=transport, access=access)

    @provide
    def get_workspace_git(self, plumbing: PackGitPlumbing) -> IPackWorkspaceGit:
        return PackWorkspaceGit(plumbing.runner, settings.git)

    @provide
    def get_pack_checker(self) -> IPackChecker:
        return WorkspacePackChecker()

    @provide
    def get_pack_hosting(self, plumbing: PackGitPlumbing) -> IPackHosting:
        return self.build_hosting(plumbing, egress=None)

    @provide
    def get_workspace_service(  # noqa: PLR0913 — порты сценария
        self,
        repo: IPackWorkspaceRepository,
        files: IPackWorkspaceFiles,
        git: IPackWorkspaceGit,
        plumbing: PackGitPlumbing,
        credentials: IGitCredentialRepository,
        policy: GitSyncPolicy,
        paths: PathMapping,
        tasks: WorkspaceTasks,
    ) -> PackWorkspaceService:
        return self.build_service(repo, files, git, plumbing.transport, credentials, policy, paths, tasks, audit=None)

    @provide
    def get_official(self, workspaces: PackWorkspaceService, access: PackStudioAccess) -> OfficialPacks:
        # Локально бота нет: официальные паки только своим токеном.
        return OfficialPacks(
            official_repo(),
            workspaces,
            access,
            None,
            default_daily_limit=settings.pack_studio.official_bot_daily_limit,
        )

    @provide(scope=Scope.REQUEST)
    def get_git_service(  # noqa: PLR0913 — порты сценария
        self,
        workspaces: PackWorkspaceService,
        git: IPackWorkspaceGit,
        plumbing: PackGitPlumbing,
        hosting: IPackHosting,
        checker: IPackChecker,
        resolver: ProviderResolver,
        author: ICommitAuthorProvider,
        policy: GitSyncPolicy,
        official: OfficialPacks,
    ) -> PackGitService:
        return self.build_git_service(
            workspaces, git, plumbing, hosting, checker, resolver, author, policy, audit=None, official=official
        )

    @staticmethod
    def build_hosting(plumbing: PackGitPlumbing, *, egress: IEgressPolicy | None) -> IPackHosting:
        local = settings.mode is StudioMode.local
        return HttpPackHosting(
            plumbing.access,
            timeout_s=settings.pack_studio.hosting_timeout_s,
            egress=egress,
            allow_insecure_http=settings.git.allow_insecure_http,
            allow_loopback_http=local and settings.git.allow_local_remotes,
        )

    @staticmethod
    def build_git_service(  # noqa: PLR0913 — те же порты, что у провайдера
        workspaces: PackWorkspaceService,
        git: IPackWorkspaceGit,
        plumbing: PackGitPlumbing,
        hosting: IPackHosting,
        checker: IPackChecker,
        resolver: ProviderResolver,
        author: ICommitAuthorProvider,
        policy: GitSyncPolicy,
        *,
        audit: IAuditLog | None,
        official: OfficialPacks | None = None,
    ) -> PackGitService:
        public_url = settings.auth.public_url
        return PackGitService(
            workspaces,
            git,
            plumbing.transport,
            hosting,
            checker,
            resolver,
            author,
            policy,
            diff_max_bytes=settings.pack_studio.max_diff_bytes,
            audit=audit,
            official=official,
            noreply_domain=noreply_domain(public_url),
            site_url=public_url.rstrip("/") if public_url else None,
        )

    @provide
    def get_files_service(self, workspaces: PackWorkspaceService, files: IPackWorkspaceFiles) -> PackFilesService:
        return PackFilesService(workspaces, files, PackYamlEditor())

    @provide
    def get_insight_service(self, workspaces: PackWorkspaceService) -> PackInsightService:
        return PackInsightService(workspaces, PackInspector())

    @provide
    def get_pack_versions(self) -> IPackVersions:
        return PackVersionWizard()

    @provide
    def get_version_service(
        self, workspaces: PackWorkspaceService, versions: IPackVersions, git: IPackWorkspaceGit
    ) -> PackVersionService:
        return PackVersionService(workspaces, versions, git)

    @provide
    def get_preview_store(self) -> IPreviewStore:
        return preview_store()

    @provide
    def get_preview_renderer(self) -> IPackPreviewRenderer:
        cfg = settings.pack_studio
        limits = PreviewRenderLimits(
            describe_timeout_s=cfg.preview_describe_timeout_s,
            materialize_timeout_s=cfg.preview_render_timeout_s,
            memory_bytes=cfg.preview_render_memory_bytes,
            stage=StageLimits(max_bytes=cfg.max_tree_bytes, max_files=cfg.max_tree_files),
        )
        return PackPreviewRenderer(previews_root() / "tmp", limits)

    @provide
    def get_preview_dispatcher(self, dispatcher: IJobDispatcher) -> IPreviewDispatcher:
        # Локально сборка предпросмотра идёт тем же встроенным раннером, что и сборки проектов.
        return PreviewJobDispatcher(dispatcher)

    @provide
    def get_preview_service(
        self,
        workspaces: PackWorkspaceService,
        renderer: IPackPreviewRenderer,
        store: IPreviewStore,
        dispatcher: IPreviewDispatcher,
    ) -> PackPreviewService:
        limits = PreviewLimits(max_concurrent=settings.pack_studio.preview_max_concurrent)
        return PackPreviewService(workspaces, renderer, store, dispatcher, limits=limits)

    @provide
    def get_places_service(self, files: PackFilesService, previews: PackPreviewService) -> PackPlacesService:
        return PackPlacesService(files, previews, PackPlacesEditor())

    @staticmethod
    def build_service(  # noqa: PLR0913 — те же порты, что у провайдера
        repo: IPackWorkspaceRepository,
        files: IPackWorkspaceFiles,
        git: IPackWorkspaceGit,
        transport: IGitTransport,
        credentials: IGitCredentialRepository,
        policy: GitSyncPolicy,
        paths: PathMapping,
        tasks: WorkspaceTasks,
        *,
        audit: IAuditLog | None,
        service_access: IServiceAccessRepository | None = None,
    ) -> PackWorkspaceService:
        cfg = settings.pack_studio
        return PackWorkspaceService(
            repo,
            files,
            git,
            transport,
            credentials,
            policy,
            paths,
            tasks,
            workspaces_dir=settings.data_dir / "pack-studio" / "workspaces",
            limits=workspace_limits(),
            max_workspaces=cfg.max_workspaces_per_user,
            default_packs_path=cfg.default_packs_path,
            local_mode=settings.mode is StudioMode.local,
            audit=audit,
            dirs_factory=workspace_dirs,
            service_access=service_access,
        )
