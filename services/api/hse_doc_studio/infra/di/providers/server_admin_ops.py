"""Провайдеры админки эксплуатации: очередь, квоты, место, политика подписи, общие ИИ-провайдеры."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import ServerConfig
from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.egress import IEgressPolicy
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.jobs.admin import IJobAdminReader
from hse_doc_studio.core.jobs.queue import IJobQueue
from hse_doc_studio.core.jobs.quotas import IQuotaOverrideRepository
from hse_doc_studio.core.jobs.runners import IRunnerRepository
from hse_doc_studio.core.storage.usage import IStorageUsageReader
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.jobs_admin import SqlJobAdminReader
from hse_doc_studio.infra.db.repositories.storage_usage import SqlStorageUsageReader
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.admin.ops_ai_providers import (
    CheckInstanceAiProviderUC,
    CreateInstanceAiProviderUC,
    DeleteInstanceAiProviderUC,
    GetInstanceAiProviderUC,
    InstanceAiProviderStore,
    ListInstanceAiProvidersUC,
    UpdateInstanceAiProviderUC,
)
from hse_doc_studio.use_cases.admin.ops_queue import CancelJobUC, ListQueueUC, QueueSummaryUC
from hse_doc_studio.use_cases.admin.ops_quotas import GetQuotasUC, QuotaService, UpdateQuotasUC
from hse_doc_studio.use_cases.admin.ops_services import ServicesOverviewUC
from hse_doc_studio.use_cases.admin.ops_signing import GetSigningPolicyUC, UpdateSigningPolicyUC
from hse_doc_studio.use_cases.admin.ops_storage import GetStorageUsageUC
from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService
from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService


class ServerAdminOpsProvider(Provider):
    scope = Scope.APP

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
        self, queue: IJobQueue, service: JobQueueService, audit: IAuditLog, uow: IUnitOfWork
    ) -> CancelJobUC:
        return CancelJobUC(queue, service, audit, uow)

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
    def get_get_signing_policy_uc(self, repo: IInstanceSettingsRepository) -> GetSigningPolicyUC:
        return GetSigningPolicyUC(repo)

    @provide
    def get_update_signing_policy_uc(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> UpdateSigningPolicyUC:
        return UpdateSigningPolicyUC(repo, audit, uow)

    @provide
    def get_instance_ai_provider_store(
        self, repo: IInstanceSettingsRepository, cipher: ISecretCipher
    ) -> InstanceAiProviderStore:
        return InstanceAiProviderStore(repo, cipher)

    @provide
    def get_list_instance_ai_providers_uc(self, store: InstanceAiProviderStore) -> ListInstanceAiProvidersUC:
        return ListInstanceAiProvidersUC(store)

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
