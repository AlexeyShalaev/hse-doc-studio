"""Серверы HSE Doc Studio в локальной Студии: вход по коду и список их проектов (только локальный контейнер)."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.git_remote.client import IStudioServerClient
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IGitHostSettingsRepository
from hse_doc_studio.infra.git_remote_client.studio_client import HttpStudioServerClient
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServerLogins, StudioServersService


class LocalGitServersProvider(Provider):
    scope = Scope.APP

    @provide
    def get_studio_client(self) -> IStudioServerClient:
        return HttpStudioServerClient(timeout_s=settings.git.token_check_timeout_s)

    @provide
    def get_studio_logins(self) -> StudioServerLogins:
        return StudioServerLogins()

    @provide
    def get_studio_servers(
        self,
        client: IStudioServerClient,
        credentials: IGitCredentialRepository,
        hosts: IGitHostSettingsRepository,
        logins: StudioServerLogins,
    ) -> StudioServersService:
        return StudioServersService(
            client, credentials, hosts, logins, allow_insecure_http=settings.git.allow_insecure_http
        )
