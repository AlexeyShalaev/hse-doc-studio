"""Сервер как git-remote: Smart HTTP, аутентификация git-токеном, права на сервис, журнал выборок."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.git_remote.protocols import IExternalChangeReconciler, IGitSmartHttp, IPushRuntime
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry
from hse_doc_studio.core.identity.protocols import IActorResolver, IApiTokenRepository, IAuditLog
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
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
from hse_doc_studio.use_cases.git_remote.receive import PushLimits, ReceivePushUC
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
