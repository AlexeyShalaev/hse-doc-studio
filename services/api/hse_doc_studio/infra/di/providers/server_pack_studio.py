"""Студия шаблонов на сервере: пространства и право «Автор шаблонов» в Postgres, включение раздела у админа, аудит."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitTransport
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.pack_studio.protocols import (
    IPackStudioGrantRepository,
    IPackStudioSectionStore,
    IPackWorkspaceFiles,
    IPackWorkspaceGit,
    IPackWorkspaceRepository,
)
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.pack_studio import (
    InstanceSectionStore,
    PostgresPackStudioGrantRepository,
    PostgresPackWorkspaceRepository,
)
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.di.providers.pack_studio import PackStudioProvider
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
