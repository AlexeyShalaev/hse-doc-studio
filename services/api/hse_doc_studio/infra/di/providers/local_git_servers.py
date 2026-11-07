"""Серверы HSE Doc Studio в локальной Студии: вход по коду и список их проектов (только локальный контейнер)."""

from __future__ import annotations

import socket

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.devices.local import IDeviceIdentity
from hse_doc_studio.core.git_remote.client import IStudioServerClient
from hse_doc_studio.core.git_remote.pdf_observer import IBuiltPdfObserver
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitHostSettingsRepository,
    IGitOperationRegistry,
    IGitRemoteRegistry,
    IGitRepoReader,
    IGitStoreRemotes,
    IGitSyncStateRepository,
)
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.remote_runner import IRemoteRunnerSupervisor
from hse_doc_studio.core.repositories import (
    IAIProviderRepository,
    ICompileRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.vcs.protocols import IVcsFolderLocks, IVcsService
from hse_doc_studio.infra.devices.identity_store import JsonDeviceIdentity
from hse_doc_studio.infra.git_remote_client.studio_client import HttpStudioServerClient
from hse_doc_studio.infra.runtime.environment import in_container
from hse_doc_studio.use_cases.devices.local_builds import LocalBuildsUC
from hse_doc_studio.use_cases.devices.local_presence import LocalPresenceService, PresenceBoard
from hse_doc_studio.use_cases.documents.get_document import GetDocumentUC
from hse_doc_studio.use_cases.git_sync.clone_project import CloneProjectUC, GetCloneDefaultsUC
from hse_doc_studio.use_cases.git_sync.cloud_projects import (
    CloneCloudProjectUC,
    CloudOpens,
    ListCloudProjectsUC,
    OpenCloudProjectUC,
)
from hse_doc_studio.use_cases.git_sync.pdf_scheduler import PdfPublishScheduler
from hse_doc_studio.use_cases.git_sync.publish_pdf import PublishPdfUC
from hse_doc_studio.use_cases.git_sync.status import GitStatusBuilder
from hse_doc_studio.use_cases.git_sync.studio_servers import StudioServerLogins, StudioServersService
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC
from hse_doc_studio.use_cases.projects.list_projects import ListProjectsUC


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
            client,
            credentials,
            hosts,
            logins,
            allow_insecure_http=settings.git.allow_insecure_http,
            local_version=settings.get_app_version(),
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
    def get_cloud_opens(self) -> CloudOpens:
        return CloudOpens()

    @provide(scope=Scope.REQUEST)
    def get_list_cloud_projects_uc(
        self, servers: StudioServersService, list_projects: ListProjectsUC
    ) -> ListCloudProjectsUC:
        return ListCloudProjectsUC(servers, list_projects)

    @provide(scope=Scope.REQUEST)
    def get_open_cloud_project_uc(  # noqa: PLR0913 — порты одного сценария
        self,
        servers: StudioServersService,
        list_projects: ListProjectsUC,
        clone: CloneProjectUC,
        defaults: GetCloneDefaultsUC,
        operations: IGitOperationRegistry,
        opens: CloudOpens,
    ) -> OpenCloudProjectUC:
        return OpenCloudProjectUC(servers, list_projects, clone, defaults, operations, opens)

    @provide(scope=Scope.REQUEST)
    def get_clone_cloud_project_uc(
        self, servers: StudioServersService, opener: OpenCloudProjectUC, operations: IGitOperationRegistry
    ) -> CloneCloudProjectUC:
        return CloneCloudProjectUC(servers, opener, operations)

    @provide
    def get_pdf_scheduler(self, publish: PublishPdfUC) -> PdfPublishScheduler:
        return PdfPublishScheduler(publish)

    @provide(override=True)
    def get_built_pdf_observer(self, scheduler: PdfPublishScheduler) -> IBuiltPdfObserver:
        return scheduler

    # --- присутствие и сборки (docs/design/connected-devices.md) ---

    @provide
    def get_device_identity(self) -> IDeviceIdentity:
        return JsonDeviceIdentity(
            settings.data_dir.expanduser(), configured_name=settings.device_name, hostname=socket.gethostname
        )

    @provide
    def get_presence_board(self) -> PresenceBoard:
        return PresenceBoard()

    @provide(scope=Scope.REQUEST)
    def get_local_presence(  # noqa: PLR0913 — порты одного сценария
        self,
        identity: IDeviceIdentity,
        servers: StudioServersService,
        registry: IGitRemoteRegistry,
        project_repo: IProjectRepository,
        store_remotes: IGitStoreRemotes,
        status: GitStatusBuilder,
        operations: IGitOperationRegistry,
        supervisor: IRemoteRunnerSupervisor,
        providers: IAIProviderRepository,
        model_lister: IAIModelLister,
        dispatcher: IJobDispatcher,
        board: PresenceBoard,
    ) -> LocalPresenceService:
        return LocalPresenceService(
            identity=identity,
            servers=servers,
            registry=registry,
            project_repo=project_repo,
            store_remotes=store_remotes,
            status=status,
            operations=operations,
            supervisor=supervisor,
            providers=providers,
            model_lister=model_lister,
            busy_building=dispatcher.has_any_active,
            board=board,
            version=settings.get_app_version(),
            os_hint=settings.device_os,
            in_container=in_container(),
        )

    @provide(scope=Scope.REQUEST)
    def get_local_builds(  # noqa: PLR0913 — порты одного сценария
        self,
        project_repo: IProjectRepository,
        project_index: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        compile_repo: ICompileRepository,
        vcs: IVcsService,
        servers: StudioServersService,
        credentials: IGitCredentialRepository,
        store_remotes: IGitStoreRemotes,
        state_repo: IGitSyncStateRepository,
    ) -> LocalBuildsUC:
        return LocalBuildsUC(
            project_uc=GetProjectUC(project_repo, project_index),
            document_uc=GetDocumentUC(project_repo, project_index, template_repo),
            project_repo=project_repo,
            compile_repo=compile_repo,
            vcs=vcs,
            servers=servers,
            credentials=credentials,
            store_remotes=store_remotes,
            state_repo=state_repo,
        )
