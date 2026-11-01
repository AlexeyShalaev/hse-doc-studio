"""Провайдеры бэкапов сервера: назначения, запуски, хранилища, части, планировщик."""

from __future__ import annotations

from pathlib import Path

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.backup.protocols import (
    IAdminDirectory,
    IBackupDestinationRepository,
    IBackupEnvironment,
    IBackupKeySource,
    IBackupPlanFactory,
    IBackupRunRepository,
    IBackupStoreFactory,
    IMaintenanceMode,
    IPartFetcher,
    IPartUploader,
    IRestoreTargetFactory,
)
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.storage import IObjectStore
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.backup.maintenance import MaintenanceController, marker_path
from hse_doc_studio.infra.backup.parts import PartFetcher, PartUploader
from hse_doc_studio.infra.backup.restore_target import RestoreTargetFactory
from hse_doc_studio.infra.backup.runtime import BackupEnvironment, BackupKeySource, BackupPlanFactory
from hse_doc_studio.infra.backup.stores import BackupStoreFactory
from hse_doc_studio.infra.db.repositories.backup import (
    SqlAdminDirectory,
    SqlBackupDestinationRepository,
    SqlBackupRunRepository,
)
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.use_cases.backup.destinations import (
    CreateDestinationUC,
    DeleteDestinationUC,
    ListDestinationsUC,
    TestDestinationUC,
    UpdateDestinationUC,
)
from hse_doc_studio.use_cases.backup.provision import ProvisionBackupUC
from hse_doc_studio.use_cases.backup.restore_admin import RestoreCoordinator
from hse_doc_studio.use_cases.backup.runs import (
    DeleteStoredBackupUC,
    GetRunUC,
    ListRunsUC,
    ListStoredBackupsUC,
    ScheduledBackupTick,
    StartBackupUC,
)
from hse_doc_studio.use_cases.backup.service import BackupService
from hse_doc_studio.use_cases.backup.settings import GetBackupSettingsUC, UpdateBackupSettingsUC


def backup_tmp_dir() -> Path:
    return (settings.backups.tmp_dir or settings.data_dir.expanduser() / "tmp" / "backup").expanduser()


class ServerBackupsProvider(Provider):
    scope = Scope.APP

    @provide
    def get_destinations(self, sessions: SessionProvider) -> IBackupDestinationRepository:
        return SqlBackupDestinationRepository(sessions)

    @provide
    def get_runs(self, sessions: SessionProvider) -> IBackupRunRepository:
        return SqlBackupRunRepository(sessions)

    @provide
    def get_admin_directory(self, sessions: SessionProvider) -> IAdminDirectory:
        return SqlAdminDirectory(sessions)

    @provide
    def get_store_factory(self) -> IBackupStoreFactory:
        return BackupStoreFactory(settings.backups, settings.s3, settings.data_dir.expanduser())

    @provide
    def get_uploader(self) -> IPartUploader:
        return PartUploader(backup_tmp_dir())

    @provide
    def get_fetcher(self) -> IPartFetcher:
        return PartFetcher(backup_tmp_dir())

    @provide
    def get_environment(self, sessions: SessionProvider) -> IBackupEnvironment:
        return BackupEnvironment(sessions)

    @provide
    def get_key_source(
        self, key_store: KeyFileStore, repo: IInstanceSettingsRepository, cipher: ISecretCipher
    ) -> IBackupKeySource:
        return BackupKeySource(key_store, repo, cipher)

    @provide
    def get_plan_factory(
        self,
        objects: IObjectStore,
        repo: IInstanceSettingsRepository,
        destinations: IBackupDestinationRepository,
        stores: IBackupStoreFactory,
        engine: AsyncEngine,
    ) -> IBackupPlanFactory:
        assert isinstance(stores, BackupStoreFactory)  # noqa: S101
        return BackupPlanFactory(settings, objects, repo, destinations, stores.local_root, backup_tmp_dir(), engine)

    @provide
    def get_service(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        repo: IInstanceSettingsRepository,
        stores: IBackupStoreFactory,
        uploader: IPartUploader,
        plans: IBackupPlanFactory,
        env: IBackupEnvironment,
        keys: IBackupKeySource,
        cipher: ISecretCipher,
        audit: IAuditLog,
        notifier: INotifier,
        admins: IAdminDirectory,
    ) -> BackupService:
        return BackupService(
            destinations, runs, repo, stores, uploader, plans, env, keys, cipher, audit, notifier, admins
        )

    @provide
    def get_maintenance(self, engine: AsyncEngine) -> IMaintenanceMode:
        return MaintenanceController(
            engine,
            marker_path(settings.data_dir.expanduser()),
            restart=settings.backups.restart_after_restore,
        )

    @provide
    def get_restore_targets(self, objects: IObjectStore) -> IRestoreTargetFactory:
        return RestoreTargetFactory(settings, objects)

    @provide
    def get_restore_coordinator(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        service: BackupService,
        keys: IBackupKeySource,
        targets: IRestoreTargetFactory,
        fetcher: IPartFetcher,
        maintenance: IMaintenanceMode,
        audit: IAuditLog,
    ) -> RestoreCoordinator:
        return RestoreCoordinator(
            destinations,
            runs,
            service,
            keys,
            targets,
            fetcher,
            maintenance,
            audit,
            apply_allowed=settings.backups.restore_from_admin,
        )

    @provide
    def get_scheduled_tick(
        self, repo: IInstanceSettingsRepository, service: BackupService, destinations: IBackupDestinationRepository
    ) -> ScheduledBackupTick:
        return ScheduledBackupTick(repo, service, destinations)

    @provide
    def get_list_destinations(self, destinations: IBackupDestinationRepository) -> ListDestinationsUC:
        return ListDestinationsUC(destinations)

    @provide
    def get_create_destination(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        cipher: ISecretCipher,
        stores: IBackupStoreFactory,
        service: BackupService,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> CreateDestinationUC:
        return CreateDestinationUC(destinations, runs, cipher, stores, service, audit, uow)

    @provide
    def get_update_destination(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        cipher: ISecretCipher,
        stores: IBackupStoreFactory,
        service: BackupService,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> UpdateDestinationUC:
        return UpdateDestinationUC(destinations, runs, cipher, stores, service, audit, uow)

    @provide
    def get_delete_destination(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        cipher: ISecretCipher,
        stores: IBackupStoreFactory,
        service: BackupService,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> DeleteDestinationUC:
        return DeleteDestinationUC(destinations, runs, cipher, stores, service, audit, uow)

    @provide
    def get_test_destination(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        cipher: ISecretCipher,
        stores: IBackupStoreFactory,
        service: BackupService,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> TestDestinationUC:
        return TestDestinationUC(destinations, runs, cipher, stores, service, audit, uow)

    @provide
    def get_get_settings(self, repo: IInstanceSettingsRepository, runs: IBackupRunRepository) -> GetBackupSettingsUC:
        return GetBackupSettingsUC(repo, runs)

    @provide
    def get_update_settings(
        self,
        repo: IInstanceSettingsRepository,
        runs: IBackupRunRepository,
        cipher: ISecretCipher,
        audit: IAuditLog,
        uow: IUnitOfWork,
    ) -> UpdateBackupSettingsUC:
        return UpdateBackupSettingsUC(repo, runs, cipher, audit, uow)

    @provide
    def get_start(self, service: BackupService) -> StartBackupUC:
        return StartBackupUC(service)

    @provide
    def get_list_runs(self, runs: IBackupRunRepository) -> ListRunsUC:
        return ListRunsUC(runs)

    @provide
    def get_get_run(self, runs: IBackupRunRepository) -> GetRunUC:
        return GetRunUC(runs)

    @provide
    def get_list_stored(
        self, destinations: IBackupDestinationRepository, service: BackupService
    ) -> ListStoredBackupsUC:
        return ListStoredBackupsUC(destinations, service)

    @provide
    def get_delete_stored(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        service: BackupService,
        audit: IAuditLog,
    ) -> DeleteStoredBackupUC:
        return DeleteStoredBackupUC(destinations, runs, service, audit)

    @provide
    def get_provision(
        self,
        destinations: IBackupDestinationRepository,
        create: CreateDestinationUC,
        settings_uc: UpdateBackupSettingsUC,
    ) -> ProvisionBackupUC:
        return ProvisionBackupUC(destinations, create, settings_uc)
