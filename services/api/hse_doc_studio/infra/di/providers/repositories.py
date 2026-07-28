from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.repositories import (
    IAgentPersonaRepository,
    IAIProviderRepository,
    IChangeLogRepository,
    IChatRepository,
    ICompileRepository,
    IFileRepository,
    IFilesystemBrowser,
    IFormStateRepository,
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ISettingsRepository,
    ISignatureRepository,
    ISigningIdentityRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.setup import (
    IDockerHealthProbe,
    IEnvironmentProbe,
    IMountProbe,
    ISelfContainerInfo,
    ISetupApplier,
)
from hse_doc_studio.core.update.repositories import (
    IReleaseNotesRepository,
    ISelfUpdateGateway,
    IUpdateCheckRepository,
    IUpdateFeedGateway,
)
from hse_doc_studio.infra.ai.agent.run_manager import AgentRunManager
from hse_doc_studio.infra.compile.compile_runner import CompileRunner
from hse_doc_studio.infra.docker.environment_probe import DockerEnvironmentProbe
from hse_doc_studio.infra.docker.mount_probe import DockerHealthProbe, MountProbe
from hse_doc_studio.infra.docker.self_info import DockerSelfInfo
from hse_doc_studio.infra.persistence.agent_persona import JsonAgentPersonaRepository
from hse_doc_studio.infra.persistence.ai_provider import JsonAIProviderRepository
from hse_doc_studio.infra.persistence.changelog import JsonChangeLogRepository
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.infra.persistence.compile import JsonCompileRepository
from hse_doc_studio.infra.persistence.files import LocalFileRepository
from hse_doc_studio.infra.persistence.filesystem_browser import LocalFilesystemBrowser
from hse_doc_studio.infra.persistence.forms import JsonFormStateRepository
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.persistence.project_index import JsonProjectIndexRepository
from hse_doc_studio.infra.persistence.settings import JsonSettingsRepository
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.infra.persistence.signing_identity import JsonSigningIdentityRepository
from hse_doc_studio.infra.persistence.submission import JsonPackSubmissionRepository
from hse_doc_studio.infra.persistence.update_check import JsonUpdateCheckRepository
from hse_doc_studio.infra.setup.applier import ContainerSetupApplier
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.infra.update.deployment import deployment_mode
from hse_doc_studio.infra.update.feed import GithubUpdateFeedGateway
from hse_doc_studio.infra.update.release_notes_file import JsonReleaseNotesRepository
from hse_doc_studio.infra.update.self_update_gateway import DockerSelfUpdateGateway
from hse_doc_studio.infra.update.update_manager import UpdateManager


class RepositoryProvider(Provider):
    scope = Scope.APP

    @provide
    def get_project_repo(self) -> IProjectRepository:
        return JsonProjectRepository()

    @provide
    def get_project_index_repo(self) -> IProjectIndexRepository:
        return JsonProjectIndexRepository(settings.data_dir.expanduser())

    @provide
    def get_template_repo(self) -> ITemplateRepository:
        repo = YamlTemplateRepository(settings.packs_dir)
        repo.load()
        return repo

    @provide
    def get_compile_repo(self) -> ICompileRepository:
        return JsonCompileRepository()

    @provide
    def get_signature_repo(self) -> ISignatureRepository:
        return JsonSignatureRepository()

    @provide
    def get_form_state_repo(self) -> IFormStateRepository:
        return JsonFormStateRepository()

    @provide
    def get_changelog_repo(self) -> IChangeLogRepository:
        return JsonChangeLogRepository()

    @provide
    def get_pack_submission_repo(self) -> IPackSubmissionRepository:
        return JsonPackSubmissionRepository()

    @provide
    def get_file_repo(self) -> IFileRepository:
        return LocalFileRepository()

    @provide
    def get_filesystem_browser(self) -> IFilesystemBrowser:
        return LocalFilesystemBrowser()

    @provide
    def get_settings_repo(self) -> ISettingsRepository:
        return JsonSettingsRepository(settings.data_dir.expanduser())

    @provide
    def get_ai_provider_repo(self) -> IAIProviderRepository:
        return JsonAIProviderRepository(settings.data_dir.expanduser())

    @provide
    def get_agent_persona_repo(self) -> IAgentPersonaRepository:
        return JsonAgentPersonaRepository(settings.data_dir.expanduser())

    @provide
    def get_chat_repo(self) -> IChatRepository:
        return JsonChatRepository()

    @provide
    def get_signing_identity_repo(self) -> ISigningIdentityRepository:
        return JsonSigningIdentityRepository(settings.data_dir.expanduser())

    @provide
    def get_release_notes_repo(self) -> IReleaseNotesRepository:
        # Scope.APP + чтение файла в конструкторе = один разбор JSON на старте
        # приложения; заметки меняются только вместе со сборкой.
        return JsonReleaseNotesRepository(settings.release_notes_file.expanduser())

    @provide
    def get_update_check_repo(self) -> IUpdateCheckRepository:
        return JsonUpdateCheckRepository(settings.data_dir.expanduser())

    @provide
    def get_self_update_gateway(
        self,
        compile_runner: CompileRunner,
        agent_runs: AgentRunManager,
    ) -> ISelfUpdateGateway:
        # Занятость читается из тех же in-memory реестров, которыми живут отмена
        # сборки и блокировка операций над папкой проекта — второго источника
        # правды о «сейчас что-то выполняется» заводить не нужно.
        return DockerSelfUpdateGateway(
            update_manager=UpdateManager(),
            compile_runner=compile_runner,
            agent_runs=agent_runs,
            deployment_mode=deployment_mode(settings.static_dir),
            image_base=settings.image_base,
        )

    @provide
    def get_docker_health_probe(self) -> IDockerHealthProbe:
        return DockerHealthProbe()

    @provide
    def get_environment_probe(self) -> IEnvironmentProbe:
        return DockerEnvironmentProbe()

    @provide
    def get_self_container_info(self) -> ISelfContainerInfo:
        return DockerSelfInfo()

    @provide
    def get_mount_probe(self) -> IMountProbe:
        return MountProbe()

    @provide
    def get_setup_applier(self) -> ISetupApplier:
        return ContainerSetupApplier(UpdateManager())

    @provide
    def get_update_feed_gateway(self) -> IUpdateFeedGateway:
        return GithubUpdateFeedGateway(
            feed_url=settings.resolved_update_feed_url(),
            timeout_s=settings.update_check_timeout_s,
            # GitHub API отклоняет запросы без User-Agent.
            user_agent=f"hse-doc-studio-update-check/{settings.get_app_version()}",
        )
