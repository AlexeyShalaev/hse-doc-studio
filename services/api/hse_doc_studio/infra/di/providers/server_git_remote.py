"""Сервер как git-remote: Smart HTTP, аутентификация git-токеном, права на сервис, журнал выборок."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.git_remote.protocols import IGitSmartHttp
from hse_doc_studio.core.identity.protocols import IActorResolver, IApiTokenRepository, IAuditLog
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository
from hse_doc_studio.infra.git_remote.smart_http import GitSmartHttp
from hse_doc_studio.use_cases.git_remote.auth import (
    AuthorizeGitServiceUC,
    GitConcurrency,
    GitFetchAudit,
    GitHttpAuthenticator,
)


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
