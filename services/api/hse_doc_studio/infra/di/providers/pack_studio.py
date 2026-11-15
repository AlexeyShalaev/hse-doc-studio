"""Студия шаблонов (docs/design/template-studio.md, срез T5): локальные провайдеры и серверные поверх них.

Локально пространства лежат в `data_dir/pack-studio/workspaces.json`, выбор «раздел включён» в `config.json`, права
раздела нет (человек один). Сервер подменяет хранилища на Postgres, включение на настройки установки и добавляет право
«Автор шаблонов» и журнал аудита.
"""

from __future__ import annotations

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
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.pack_studio.protocols import (
    IPackChecker,
    IPackHosting,
    IPackStudioSectionStore,
    IPackWorkspaceFiles,
    IPackWorkspaceGit,
    IPackWorkspaceRepository,
    IServiceAccessRepository,
    WorkspaceLimits,
)
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.repositories import ISettingsRepository
from hse_doc_studio.core.vcs.protocols import ICommitAuthorProvider
from hse_doc_studio.infra.pack_studio.hosting import HttpPackHosting
from hse_doc_studio.infra.pack_studio.local_store import JsonPackWorkspaceRepository, LocalSectionStore
from hse_doc_studio.infra.pack_studio.plumbing import PackGitPlumbing
from hse_doc_studio.infra.pack_studio.workspace_check import WorkspacePackChecker
from hse_doc_studio.infra.pack_studio.workspace_files import LocalPackWorkspaceFiles
from hse_doc_studio.infra.pack_studio.workspace_git import PackWorkspaceGit, workspace_dirs
from hse_doc_studio.infra.pack_studio.yaml_edits import PackYamlEditor
from hse_doc_studio.use_cases.git_sync.provider_resolver import ProviderResolver
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.git import PackGitService
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
    ) -> PackGitService:
        return self.build_git_service(workspaces, git, plumbing, hosting, checker, resolver, author, policy, audit=None)

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
    ) -> PackGitService:
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
        )

    @provide
    def get_files_service(self, workspaces: PackWorkspaceService, files: IPackWorkspaceFiles) -> PackFilesService:
        return PackFilesService(workspaces, files, PackYamlEditor())

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
