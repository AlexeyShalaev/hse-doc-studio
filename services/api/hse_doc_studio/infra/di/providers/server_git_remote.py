"""Сервер как git-remote: Smart HTTP, аутентификация git-токеном, права на сервис, журнал выборок."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.git_remote.protocols import IExternalChangeReconciler, IGitSmartHttp, IPushRuntime
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, ISecretCipher
from hse_doc_studio.core.identity.protocols import IActorResolver, IApiTokenRepository, IAuditLog
from hse_doc_studio.core.projects.browse import IProjectBrowser
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.infra.db.repositories.device_authorizations import SqlDeviceAuthorizationRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.git_remote.push_runtime import GitPushRuntime
from hse_doc_studio.infra.git_remote.reconciler import ExternalChangeReconciler
from hse_doc_studio.infra.git_remote.smart_http import GitSmartHttp
from hse_doc_studio.infra.projects.catalog_sync import ProjectCatalogMirror
from hse_doc_studio.use_cases.git_remote.auth import (
    AuthorizeGitServiceUC,
    GitConcurrency,
    GitFetchAudit,
    GitHttpAuthenticator,
)
from hse_doc_studio.use_cases.git_remote.projects import GetProjectGitRemoteUC, ListGitProjectsUC
from hse_doc_studio.use_cases.git_remote.receive import PushLimits, ReceivePushUC
from hse_doc_studio.use_cases.identity.api_tokens import CreateApiTokenUC, RevokeApiTokenUC
from hse_doc_studio.use_cases.identity.device_flow import DeviceFlowService
from hse_doc_studio.use_cases.projects.get_project_access import GetProjectAccessUC


class ServerGitRemoteProvider(Provider):
    scope = Scope.APP

    @provide
    def get_smart_http(self) -> IGitSmartHttp:
        cfg = settings.git_remote
        return GitSmartHttp(max_body_bytes=cfg.max_push_bytes, timeout_s=cfg.timeout_s)

    @provide
    def get_git_authenticator(
        self, resolver: IActorResolver, tokens: IApiTokenRepository, audit: IAuditLog
    ) -> GitHttpAuthenticator:
        return GitHttpAuthenticator(resolver, tokens, audit)

    @provide
    def get_git_concurrency(self) -> GitConcurrency:
        return GitConcurrency(settings.git_remote.max_concurrent_per_user)

    @provide
    def get_git_fetch_audit(self, audit: IAuditLog) -> GitFetchAudit:
        return GitFetchAudit(audit)

    @provide(scope=Scope.REQUEST)
    def get_authorize_git_service(
        self, acl: IProjectAclRepository, project_repo: IProjectRepository, project_index: IProjectIndexRepository
    ) -> AuthorizeGitServiceUC:
        return AuthorizeGitServiceUC(acl, project_repo, project_index)

    @provide
    def get_push_runtime(self) -> IPushRuntime:
        return GitPushRuntime()

    @provide
    def get_external_change_reconciler(
        self, projects: IProjectRepository, mirror: ProjectCatalogMirror
    ) -> IExternalChangeReconciler:
        return ExternalChangeReconciler(projects, mirror)

    @provide(scope=Scope.REQUEST)
    def get_receive_push(  # noqa: PLR0913 — порты одного приёма
        self,
        project_access: GetProjectAccessUC,
        operations: IGitOperationRegistry,
        locks: IVcsFolderLocks,
        vcs: IVcsService,
        runtime: IPushRuntime,
        reconciler: IExternalChangeReconciler,
        audit: IAuditLog,
    ) -> ReceivePushUC:
        cfg = settings.git_remote
        limits = PushLimits(max_push_bytes=cfg.max_push_bytes, lock_wait_s=cfg.lock_wait_s)
        return ReceivePushUC(project_access, operations, locks, vcs, runtime, reconciler, audit, limits)

    @provide(scope=Scope.REQUEST)
    def get_list_git_projects(self, browser: IProjectBrowser, acl: IProjectAclRepository) -> ListGitProjectsUC:
        return ListGitProjectsUC(browser, acl, public_base_url())

    @provide(scope=Scope.REQUEST)
    def get_project_git_remote(
        self,
        acl: IProjectAclRepository,
        project_repo: IProjectRepository,
        project_index: IProjectIndexRepository,
        vcs: IVcsService,
    ) -> GetProjectGitRemoteUC:
        return GetProjectGitRemoteUC(
            acl, project_repo, project_index, vcs, enabled=settings.git_remote.enabled, public_url=public_base_url()
        )

    @provide
    def get_device_flow(  # noqa: PLR0913 — порты одного сценария
        self,
        sessions: SessionProvider,
        create_token: CreateApiTokenUC,
        revoke_token: RevokeApiTokenUC,
        cipher: ISecretCipher,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> DeviceFlowService:
        return DeviceFlowService(
            SqlDeviceAuthorizationRepository(sessions), create_token, revoke_token, cipher, audit, uow
        )


def public_base_url() -> str:
    """Внешний адрес сервера для ссылок клонирования; без public_url остаётся адрес по умолчанию."""
    return (settings.auth.public_url or f"http://{settings.server.host}:{settings.server.port}").rstrip("/")
