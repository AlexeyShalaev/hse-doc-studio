"""Провайдеры админки эксплуатации: очередь, квоты, место, политика подписи, общие ИИ-провайдеры."""

from __future__ import annotations

from dishka import AsyncContainer, Provider, Scope, provide

from hse_doc_studio.api.config import ServerConfig, settings
from hse_doc_studio.api.runner_install import render_install_script
from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.ai_runtime import IHardwareProbe
from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.identity.instance_settings import InstanceEnvOverrides
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.jobs.admin import IAdminProjectPicker, IJobAdminReader, IRunnerAdminReader
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.quotas import IQuotaOverrideRepository
from hse_doc_studio.core.jobs.runners import IRunnerRepository
from hse_doc_studio.core.model_servers import (
    Engine,
    IContainerRuntime,
    IHostResources,
    IModelProviderRegistry,
    IModelServerClient,
)
from hse_doc_studio.core.repositories import IAIProviderRepository, IInstanceAiProviderDirectory
from hse_doc_studio.core.runner_install import ILocalRunnerHost, InstallTarget
from hse_doc_studio.core.signatures.key_policy import IServerKeyCounter
from hse_doc_studio.core.storage.usage import IStorageUsageReader
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.ai_providers import PostgresAIProviderRepository
from hse_doc_studio.infra.db.repositories.jobs_admin import SqlAdminProjectPicker, SqlJobAdminReader
from hse_doc_studio.infra.db.repositories.runner_ssh_credentials import PostgresSshCredentialRepository
from hse_doc_studio.infra.db.repositories.runners import SqlRunnerAdminReader
from hse_doc_studio.infra.db.repositories.signing_key_policy import SqlServerKeyCounter
from hse_doc_studio.infra.db.repositories.storage_usage import SqlStorageUsageReader
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.docker.siblings import SiblingNetwork
from hse_doc_studio.infra.model_servers.client import HttpModelServerClient
from hse_doc_studio.infra.model_servers.docker_runtime import DockerContainerRuntime
from hse_doc_studio.infra.model_servers.host_resources import LocalHostResources
from hse_doc_studio.infra.model_servers.provider_registry import ContainerProviderRegistry
from hse_doc_studio.use_cases.admin.model_servers import (
    HfTokenVault,
    ModelServerService,
    ModelServerSettings,
    ModelServersUC,
)

from hse_doc_studio.infra.egress.policy import ResolvingEgressPolicy
from hse_doc_studio.infra.runner_install.docker_host import DockerLocalHost
from hse_doc_studio.infra.runner_install.kube_host import KubeLocalHost
from hse_doc_studio.infra.runner_install.ssh_connector import AsyncSshConnector
from hse_doc_studio.use_cases.admin.ops_ai_providers import (
    CheckInstanceAiProviderUC,
    CreateInstanceAiProviderUC,
    DeleteInstanceAiProviderUC,
    GetInstanceAiProviderUC,
    InstanceAiProviderStore,
    ListInstanceAiProvidersUC,
    UpdateInstanceAiProviderUC,
)
from hse_doc_studio.use_cases.admin.ops_install import (
    GetInstanceSettingsUC,
    UpdateBuildSettingsUC,
    UpdateInstanceSettingsUC,
)
from hse_doc_studio.use_cases.admin.ops_queue import CancelJobUC, ListQueueUC, PickProjectsUC, QueueSummaryUC
from hse_doc_studio.use_cases.admin.ops_quotas import GetQuotasUC, QuotaService, UpdateQuotasUC
from hse_doc_studio.use_cases.admin.ops_runners import (
    ListRegistrationTokensUC,
    ListRunnersUC,
    PickRunnersUC,
    RunnerSummaryUC,
)
from hse_doc_studio.use_cases.admin.ops_services import ServicesOverviewUC
from hse_doc_studio.use_cases.admin.ops_signing import GetSigningPolicyUC, UpdateSigningPolicyUC
from hse_doc_studio.use_cases.admin.ops_storage import GetStorageUsageUC, ListStorageOwnersUC
from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService
from hse_doc_studio.use_cases.jobs.personal_settings import InstancePersonalRunnerSettings
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry
from hse_doc_studio.use_cases.runner_install import (
    InstallJobStore,
    RunnerInstallService,
    SshInstallService,
    SshSessionStore,
)


class ServerAdminOpsProvider(Provider):
    scope = Scope.APP

    @provide
    def get_instance_env_overrides(self) -> InstanceEnvOverrides:
        return InstanceEnvOverrides(
            name=settings.server.instance_name,
            public_url=settings.auth.public_url,
            docs_url=settings.server.docs_url,
            landing_enabled=settings.server.landing_enabled,
            build_timeout_s=settings.jobs.build_timeout_s,
            artifact_retention_days=settings.jobs.artifact_retention_days,
            personal_runners_enabled=settings.jobs.personal_runners_enabled,
            personal_runner_wait_s=settings.jobs.personal_runner_wait_s,
            personal_runners_max_per_user=settings.jobs.personal_runners_max_per_user,
        )

    @provide
    def get_get_instance_settings_uc(
        self, repo: IInstanceSettingsRepository, env: InstanceEnvOverrides
    ) -> GetInstanceSettingsUC:
        return GetInstanceSettingsUC(repo, env)

    @provide
    def get_update_instance_settings_uc(
        self,
        repo: IInstanceSettingsRepository,
        env: InstanceEnvOverrides,
        audit: IAuditLog,
        uow: IUnitOfWork,
        read: GetInstanceSettingsUC,
    ) -> UpdateInstanceSettingsUC:
        return UpdateInstanceSettingsUC(repo, env, audit, uow, read)

    @provide
    def get_update_build_settings_uc(
        self,
        repo: IInstanceSettingsRepository,
        env: InstanceEnvOverrides,
        audit: IAuditLog,
        uow: IUnitOfWork,
        read: GetInstanceSettingsUC,
        personal: InstancePersonalRunnerSettings,
        queue: JobQueueService,
    ) -> UpdateBuildSettingsUC:
        return UpdateBuildSettingsUC(repo, env, audit, uow, read, personal=personal, queue=queue)

    @provide
    def get_job_admin_reader(self, sessions: SessionProvider) -> IJobAdminReader:
        return SqlJobAdminReader(sessions)

    @provide
    def get_storage_usage_reader(self, sessions: SessionProvider, server_config: ServerConfig) -> IStorageUsageReader:
        return SqlStorageUsageReader(sessions, server_config.projects_root)

    @provide
    def get_quota_service(self, repo: IInstanceSettingsRepository, overrides: IQuotaOverrideRepository) -> QuotaService:
        return QuotaService(repo, overrides)

    @provide
    def get_list_queue_uc(self, reader: IJobAdminReader) -> ListQueueUC:
        return ListQueueUC(reader)

    @provide
    def get_queue_summary_uc(self, reader: IJobAdminReader) -> QueueSummaryUC:
        return QueueSummaryUC(reader)

    @provide
    def get_cancel_job_uc(
        self, queue: IJobQueue, service: JobQueueService, audit: IAuditLog, uow: IUnitOfWork, reader: IJobAdminReader
    ) -> CancelJobUC:
        return CancelJobUC(queue, service, audit, uow, reader)

    @provide
    def get_admin_project_picker(self, sessions: SessionProvider) -> IAdminProjectPicker:
        return SqlAdminProjectPicker(sessions)

    @provide
    def get_pick_projects_uc(self, picker: IAdminProjectPicker) -> PickProjectsUC:
        return PickProjectsUC(picker)

    @provide
    def get_runner_admin_reader(self, sessions: SessionProvider) -> IRunnerAdminReader:
        return SqlRunnerAdminReader(sessions)

    @provide
    def get_list_runners_uc(self, reader: IRunnerAdminReader) -> ListRunnersUC:
        return ListRunnersUC(reader)

    @provide
    def get_runner_summary_uc(self, reader: IRunnerAdminReader) -> RunnerSummaryUC:
        return RunnerSummaryUC(reader)

    @provide
    def get_list_registration_tokens_uc(self, reader: IRunnerAdminReader) -> ListRegistrationTokensUC:
        return ListRegistrationTokensUC(reader)

    @provide
    def get_pick_runners_uc(self, reader: IRunnerAdminReader) -> PickRunnersUC:
        return PickRunnersUC(reader)

    @provide
    def get_get_quotas_uc(self, repo: IInstanceSettingsRepository) -> GetQuotasUC:
        return GetQuotasUC(repo)

    @provide
    def get_update_quotas_uc(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, service: QuotaService
    ) -> UpdateQuotasUC:
        return UpdateQuotasUC(repo, audit, uow, service)

    @provide
    def get_services_overview_uc(self, runners: IRunnerRepository, smtp: SmtpSettingsService) -> ServicesOverviewUC:
        return ServicesOverviewUC(runners, smtp)

    @provide
    def get_storage_usage_uc(self, reader: IStorageUsageReader) -> GetStorageUsageUC:
        return GetStorageUsageUC(reader)

    @provide
    def get_list_storage_owners_uc(self, reader: IStorageUsageReader) -> ListStorageOwnersUC:
        return ListStorageOwnersUC(reader)

    @provide
    def get_server_key_counter(self, sessions: SessionProvider) -> IServerKeyCounter:
        return SqlServerKeyCounter(sessions)

    @provide
    def get_get_signing_policy_uc(
        self, repo: IInstanceSettingsRepository, counter: IServerKeyCounter
    ) -> GetSigningPolicyUC:
        return GetSigningPolicyUC(repo, counter)

    @provide
    def get_update_signing_policy_uc(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, counter: IServerKeyCounter
    ) -> UpdateSigningPolicyUC:
        return UpdateSigningPolicyUC(repo, audit, uow, counter)

    @provide
    def get_instance_ai_provider_store(self, repo: IAIProviderRepository) -> InstanceAiProviderStore:
        return InstanceAiProviderStore(repo)

    @provide
    def get_instance_ai_provider_directory(
        self, sessions: SessionProvider, cipher: ISecretCipher
    ) -> IInstanceAiProviderDirectory:
        return PostgresAIProviderRepository(sessions, cipher)

    @provide
    def get_list_instance_ai_providers_uc(self, directory: IInstanceAiProviderDirectory) -> ListInstanceAiProvidersUC:
        return ListInstanceAiProvidersUC(directory)

    @provide
    def get_get_instance_ai_provider_uc(self, store: InstanceAiProviderStore) -> GetInstanceAiProviderUC:
        return GetInstanceAiProviderUC(store)

    @provide
    def get_create_instance_ai_provider_uc(
        self, store: InstanceAiProviderStore, audit: IAuditLog, uow: IUnitOfWork, egress: IEgressPolicy
    ) -> CreateInstanceAiProviderUC:
        return CreateInstanceAiProviderUC(store, audit, uow, egress)

    @provide
    def get_update_instance_ai_provider_uc(
        self, store: InstanceAiProviderStore, audit: IAuditLog, uow: IUnitOfWork, egress: IEgressPolicy
    ) -> UpdateInstanceAiProviderUC:
        return UpdateInstanceAiProviderUC(store, audit, uow, egress)

    @provide
    def get_delete_instance_ai_provider_uc(
        self, store: InstanceAiProviderStore, audit: IAuditLog, uow: IUnitOfWork
    ) -> DeleteInstanceAiProviderUC:
        return DeleteInstanceAiProviderUC(store, audit, uow)

    @provide
    def get_check_instance_ai_provider_uc(
        self, store: InstanceAiProviderStore, lister: IAIModelLister
    ) -> CheckInstanceAiProviderUC:
        return CheckInstanceAiProviderUC(store, lister)

    # ── серверы ИИ-моделей ────────────────────────────────────────────────

    @provide
    def get_container_runtime(self, siblings: SiblingNetwork) -> IContainerRuntime:
        return DockerContainerRuntime(siblings)

    @provide
    def get_model_server_client(self) -> IModelServerClient:
        return HttpModelServerClient()

    @provide
    def get_host_resources(self) -> IHostResources:
        return LocalHostResources(settings.data_dir)

    @provide
    def get_model_provider_registry(self, container: AsyncContainer) -> IModelProviderRegistry:
        return ContainerProviderRegistry(container)

    @provide
    def get_model_server_service(  # noqa: PLR0913 — порты
        self,
        runtime: IContainerRuntime,
        client: IModelServerClient,
        hardware: IHardwareProbe,
        resources: IHostResources,
        registry: IModelProviderRegistry,
        vault: HfTokenVault,
    ) -> ModelServerService:
        cfg = settings.model_servers
        images = {
            Engine.ollama: cfg.ollama_image,
            Engine.vllm: cfg.vllm_image,
            Engine.sglang: cfg.sglang_image,
        }
        return ModelServerService(
            runtime,
            client,
            hardware,
            resources,
            registry,
            ModelServerSettings(
                local_enabled=cfg.local_enabled,
                images={e: i for e, i in images.items() if i},
                max_concurrent_installs=cfg.max_concurrent_installs,
                startup_timeout_s=cfg.startup_timeout_s,
                ready_timeout_s=cfg.ready_timeout_s,
            ),
            vault,
        )

    @provide
    def get_hf_token_vault(self, repo: IInstanceSettingsRepository, cipher: ISecretCipher) -> HfTokenVault:
        return HfTokenVault(repo, cipher)

    @provide
    def get_model_servers_uc(
        self, service: ModelServerService, audit: IAuditLog, vault: HfTokenVault, uow: IUnitOfWork
    ) -> ModelServersUC:
        return ModelServersUC(service, audit, vault, uow)

    @provide
    def get_install_job_store(self) -> InstallJobStore:
        return InstallJobStore()

    @provide
    def get_runner_install_service(
        self, registry: RunnerRegistry, jobs: InstallJobStore, audit: IAuditLog, uow: IUnitOfWork
    ) -> RunnerInstallService:
        cfg = settings.runner_install
        hosts: dict[InstallTarget, ILocalRunnerHost] = {
            InstallTarget.docker: DockerLocalHost(enabled=cfg.docker_enabled),
            InstallTarget.kubernetes: KubeLocalHost(
                enabled=cfg.kubernetes_enabled,
                service_account=cfg.kubernetes_service_account,
                storage_class=cfg.kubernetes_storage_class,
                storage_size=cfg.kubernetes_storage_size,
            ),
        }
        return RunnerInstallService(
            registry,
            hosts,
            jobs,
            audit,
            uow,
            image=f"{settings.image_base}:{settings.get_app_version()}",
            data_dir=cfg.data_dir,
            internal_urls={InstallTarget.kubernetes: cfg.kubernetes_studio_url} if cfg.kubernetes_studio_url else None,
        )

    @provide
    def get_ssh_session_store(self) -> SshSessionStore:
        return SshSessionStore()

    @provide
    def get_ssh_install_service(  # noqa: PLR0913
        self,
        registry: RunnerRegistry,
        sessions: SshSessionStore,
        jobs: InstallJobStore,
        audit: IAuditLog,
        uow: IUnitOfWork,
        db: SessionProvider,
        cipher: ISecretCipher,
    ) -> SshInstallService:
        cfg = settings.runner_install
        # Своя политика: частные сети и адреса кластера закрыты, пока админ не внёс их в allowlist; метаданные облака
        # закрыты всегда.
        egress = ResolvingEgressPolicy([*settings.egress.allowlist, *cfg.ssh_allowlist])
        return SshInstallService(
            registry,
            AsyncSshConnector(),
            egress,
            sessions,
            jobs,
            audit,
            uow,
            PostgresSshCredentialRepository(db, cipher) if cfg.ssh_save_credentials else None,
            enabled=cfg.ssh_enabled,
            image=f"{settings.image_base}:{settings.get_app_version()}",
            script=render_install_script,
            data_dir=cfg.data_dir,
        )
