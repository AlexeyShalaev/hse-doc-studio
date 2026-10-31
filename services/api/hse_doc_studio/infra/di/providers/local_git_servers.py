"""Серверы HSE Doc Studio в локальной Студии: вход по коду и список их проектов (только локальный контейнер)."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.git_remote.client import IStudioServerClient
from hse_doc_studio.core.git_remote.pdf_observer import IBuiltPdfObserver
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitHostSettingsRepository,
    IGitRepoReader,
    IGitStoreRemotes,
    IGitSyncStateRepository,
)
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks
from hse_doc_studio.infra.git_remote_client.studio_client import HttpStudioServerClient
from hse_doc_studio.use_cases.documents.get_document import GetDocumentUC
from hse_doc_studio.use_cases.git_sync.pdf_scheduler import PdfPublishScheduler
from hse_doc_studio.use_cases.git_sync.publish_pdf import PublishPdfUC
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServerLogins, StudioServersService
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC


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

    @provide
    def get_publish_pdf_uc(  # noqa: PLR0913 — порты одного сценария
        self,
        project_repo: IProjectRepository,
        project_index: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
        credentials: IGitCredentialRepository,
        servers: StudioServersService,
        reader: IGitRepoReader,
        locks: IVcsFolderLocks,
        policy: GitSyncPolicy,
    ) -> PublishPdfUC:
        return PublishPdfUC(
            project_repo_uc=GetProjectUC(project_repo, project_index),
            document_uc=GetDocumentUC(project_repo, project_index, template_repo),
            store_remotes=store_remotes,
            state_repo=state_repo,
            credentials=credentials,
            servers=servers,
            reader=reader,
            locks=locks,
            policy=policy,
        )

    @provide
    def get_pdf_scheduler(self, publish: PublishPdfUC) -> PdfPublishScheduler:
        return PdfPublishScheduler(publish)

    @provide(override=True)
    def get_built_pdf_observer(self, scheduler: PdfPublishScheduler) -> IBuiltPdfObserver:
        return scheduler
