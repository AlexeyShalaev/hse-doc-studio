"""Провайдеры квот этапа 6: счётчики расхода, расход владельцев, допуск, использование и админка квот."""

from __future__ import annotations

from dishka import AnyOf, Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.ai_gateway.usage import IAiUsageLog
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository, IUserRepository
from hse_doc_studio.core.jobs.quotas import IQuotaOverrideRepository
from hse_doc_studio.core.orgs.protocols import IOrgRepository
from hse_doc_studio.core.quotas.protocols import IOwnerFootprint, IQuotaGate, IUsageCounters
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.usage_counters import SqlOwnerFootprint, SqlUsageCounters
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.use_cases.admin.ops_quota_policy import (
    AdminOwnerUsageUC,
    AdminUsageSummaryUC,
    DeleteQuotaOverrideUC,
    GetQuotaPolicyUC,
    ListQuotaOverridesUC,
    ResetUsageUC,
    SetQuotaOverrideUC,
    UpdateQuotaPolicyUC,
)
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.quotas.gate import QuotaGate
from hse_doc_studio.use_cases.quotas.housekeeping import QuotaHousekeeping
from hse_doc_studio.use_cases.quotas.usage import GetMyUsageUC, GetOrgUsageUC


class ServerQuotasProvider(Provider):
    scope = Scope.APP

    @provide
    def get_usage_counters(self, sessions: SessionProvider) -> IUsageCounters:
        return SqlUsageCounters(sessions)

    @provide
    def get_owner_footprint(self, sessions: SessionProvider) -> IOwnerFootprint:
        return SqlOwnerFootprint(sessions)

    @provide
    def get_quota_gate(
        self, quotas: QuotaService, counters: IUsageCounters, footprint: IOwnerFootprint
    ) -> AnyOf[QuotaGate, IQuotaGate]:
        return QuotaGate(quotas, counters, footprint)

    @provide
    def get_my_usage_uc(self, gate: QuotaGate, orgs: IOrgRepository) -> GetMyUsageUC:
        return GetMyUsageUC(gate, orgs)

    @provide
    def get_org_usage_uc(self, gate: QuotaGate, orgs: IOrgRepository) -> GetOrgUsageUC:
        return GetOrgUsageUC(gate, orgs)

    @provide
    def get_quota_policy_uc(self, repo: IInstanceSettingsRepository) -> GetQuotaPolicyUC:
        return GetQuotaPolicyUC(repo)

    @provide
    def get_update_quota_policy_uc(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, service: QuotaService
    ) -> UpdateQuotaPolicyUC:
        return UpdateQuotaPolicyUC(repo, audit, uow, service)

    @provide
    def get_list_overrides_uc(
        self, overrides: IQuotaOverrideRepository, users: IUserRepository, orgs: IOrgRepository
    ) -> ListQuotaOverridesUC:
        return ListQuotaOverridesUC(overrides, users, orgs)

    @provide
    def get_set_override_uc(
        self,
        overrides: IQuotaOverrideRepository,
        users: IUserRepository,
        orgs: IOrgRepository,
        audit: IAuditLog,
        uow: IUnitOfWork,
        service: QuotaService,
    ) -> SetQuotaOverrideUC:
        return SetQuotaOverrideUC(overrides, users, orgs, audit, uow, service)

    @provide
    def get_delete_override_uc(
        self, overrides: IQuotaOverrideRepository, audit: IAuditLog, uow: IUnitOfWork, service: QuotaService
    ) -> DeleteQuotaOverrideUC:
        return DeleteQuotaOverrideUC(overrides, audit, uow, service)

    @provide
    def get_admin_owner_usage_uc(
        self, gate: QuotaGate, users: IUserRepository, orgs: IOrgRepository
    ) -> AdminOwnerUsageUC:
        return AdminOwnerUsageUC(gate, users, orgs)

    @provide
    def get_admin_usage_summary_uc(
        self, gate: QuotaGate, users: IUserRepository, orgs: IOrgRepository
    ) -> AdminUsageSummaryUC:
        return AdminUsageSummaryUC(gate, users, orgs)

    @provide
    def get_reset_usage_uc(
        self, gate: QuotaGate, users: IUserRepository, orgs: IOrgRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> ResetUsageUC:
        return ResetUsageUC(gate, users, orgs, audit, uow)

    @provide
    def get_quota_housekeeping(self, counters: IUsageCounters, usage: IAiUsageLog) -> QuotaHousekeeping:
        return QuotaHousekeeping(counters, usage, usage_retention_days=settings.ai_gateway.usage_retention_days)
