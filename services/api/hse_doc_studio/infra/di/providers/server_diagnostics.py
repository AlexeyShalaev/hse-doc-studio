"""Провайдеры самодиагностики: пробы, реестр проверок, сервис прогона и сценарии админки."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.background import BackgroundTaskRunner
from hse_doc_studio.core.backup.protocols import IBackupDestinationRepository
from hse_doc_studio.core.diagnostics.entities import CheckId
from hse_doc_studio.core.diagnostics.ports import IDiagCheck, IDiagStore
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.jobs.autoscale import IQueueMetricsReader
from hse_doc_studio.core.lifecycle.ports import IAdminDirectory, ILifecycleRuns
from hse_doc_studio.core.storage import IObjectStore
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.diagnostics import SqlDiagStore
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.diagnostics.probes import (
    BackupProbe,
    DatabaseProbe,
    JobProbe,
    MigrationProbe,
    ObjectProbe,
    RunnerProbe,
    SchedulerProbe,
    SmtpProbe,
    TlsProbe,
)
from hse_doc_studio.use_cases.diagnostics.admin import (
    GetDiagnosticsUC,
    RunDiagnosticsUC,
    UpdateDiagnosticsThresholdsUC,
)
from hse_doc_studio.use_cases.diagnostics.checks import (
    BackupsCheck,
    DatabaseCheck,
    DiskCheck,
    JobsCheck,
    MigrationsCheck,
    ObjectStorageCheck,
    RunnersCheck,
    SchedulerCheck,
    SmtpCheck,
    TlsCheck,
)
from hse_doc_studio.use_cases.diagnostics.service import DiagnosticsService
from hse_doc_studio.use_cases.identity.smtp_settings import SmtpSettingsService
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard


class BackgroundHolder:
    """Раннер фоновых задач подключается при старте приложения (контейнер собирается раньше)."""

    def __init__(self) -> None:
        self.runner: BackgroundTaskRunner | None = None


def _s3_urls() -> list[str]:
    s3 = settings.s3
    found = [u for u in (s3.endpoint, s3.public_endpoint) if u]
    return list(dict.fromkeys(found)) if s3.bucket else []


class ServerDiagnosticsProvider(Provider):
    scope = Scope.APP

    @provide
    def get_background_holder(self) -> BackgroundHolder:
        return BackgroundHolder()

    @provide
    def get_store(self, sessions: SessionProvider) -> IDiagStore:
        return SqlDiagStore(sessions)

    @provide
    def get_service(
        self,
        sessions: SessionProvider,
        object_store: IObjectStore,
        metrics: IQueueMetricsReader,
        guard: StorageGuard,
        instance_settings: IInstanceSettingsRepository,
        engine: LifecycleEngine,
        runs: ILifecycleRuns,
        destinations: IBackupDestinationRepository,
        smtp: SmtpSettingsService,
        holder: BackgroundHolder,
        store: IDiagStore,
        notifier: INotifier,
        admins: IAdminDirectory,
    ) -> DiagnosticsService:
        cfg = settings.diagnostics
        tls = TlsProbe()
        public = settings.auth.public_url
        checks: list[IDiagCheck] = [
            DatabaseCheck(DatabaseProbe(sessions)),
            MigrationsCheck(MigrationProbe(sessions)),
            ObjectStorageCheck(ObjectProbe(object_store, bucket=settings.s3.bucket)),
            DiskCheck(guard, instance_settings, engine, runs),
            RunnersCheck(RunnerProbe(sessions, metrics)),
            JobsCheck(JobProbe(sessions, metrics)),
            SchedulerCheck(SchedulerProbe(sessions, lambda: holder.runner), instance_settings, cfg.interval_s),
            TlsCheck(CheckId.tls_public, tls, lambda: [public] if public else []),
            TlsCheck(CheckId.tls_s3, tls, _s3_urls),
            BackupsCheck(
                BackupProbe(sessions), instance_settings, destinations, feature_enabled=settings.backups.enabled
            ),
            SmtpCheck(SmtpProbe(smtp.params)),
        ]
        return DiagnosticsService(checks, store, instance_settings, notifier, admins, timeout_s=cfg.check_timeout_s)

    @provide
    def get_get_uc(
        self, service: DiagnosticsService, instance_settings: IInstanceSettingsRepository
    ) -> GetDiagnosticsUC:
        cfg = settings.diagnostics
        return GetDiagnosticsUC(service, instance_settings, interval_s=cfg.interval_s, enabled=cfg.enabled)

    @provide
    def get_run_uc(self, service: DiagnosticsService, get: GetDiagnosticsUC, audit: IAuditLog) -> RunDiagnosticsUC:
        return RunDiagnosticsUC(service, get, audit)

    @provide
    def get_update_uc(
        self, instance_settings: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, get: GetDiagnosticsUC
    ) -> UpdateDiagnosticsThresholdsUC:
        return UpdateDiagnosticsThresholdsUC(instance_settings, audit, uow, get)
