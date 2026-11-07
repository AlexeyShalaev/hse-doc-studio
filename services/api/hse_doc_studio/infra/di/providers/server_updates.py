"""Провайдеры автообновления сервера."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.backup.protocols import IAdminDirectory, IBackupDestinationRepository, IBackupRunRepository
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.server_update.options import UpdateOptions
from hse_doc_studio.core.server_update.protocols import IReleaseSource, IUpdateRunRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.repositories.server_update import SqlUpdateRunRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.update.feed import GithubUpdateFeedGateway
from hse_doc_studio.infra.update.release_source import FeedReleaseSource
from hse_doc_studio.use_cases.backup.service import BackupService
from hse_doc_studio.use_cases.server_update.admin import UpdateAdmin
from hse_doc_studio.use_cases.server_update.service import UpdateService


def _db_head() -> str | None:
    """Head миграций этого образа: база работающего api стоит именно на нём (иначе api не стартовал бы)."""
    try:
        return migrator.head_revision()
    except Exception:  # noqa: BLE001 — без head откат на выбранную версию просто проверяется только апдейтером
        return None


class ServerUpdatesProvider(Provider):
    scope = Scope.APP

    @provide
    def get_runs(self, sessions: SessionProvider) -> IUpdateRunRepository:
        return SqlUpdateRunRepository(sessions)

    @provide
    def get_source(self) -> IReleaseSource:
        return FeedReleaseSource(
            GithubUpdateFeedGateway(
                feed_url=settings.resolved_update_feed_url(),
                timeout_s=settings.update_check_timeout_s,
                user_agent=f"hse-doc-studio-update-check/{settings.get_app_version()}",
            )
        )

    @provide
    def get_options(self) -> UpdateOptions:
        cfg = settings.server_update
        return UpdateOptions(
            current_version=settings.get_app_version(),
            db_head=_db_head(),
            executor_enabled=cfg.enabled
            and cfg.executor in {"compose", "kubernetes"}
            and bool(cfg.updater_token.get_secret_value()),
            executor=cfg.executor,
            check_interval_s=cfg.check_interval_s,
            updater_stale_s=cfg.updater_stale_s,
            run_lost_s=cfg.run_lost_s,
        )

    @provide
    def get_service(  # noqa: PLR0913
        self,
        runs: IUpdateRunRepository,
        repo: IInstanceSettingsRepository,
        source: IReleaseSource,
        backup: BackupService,
        backup_runs: IBackupRunRepository,
        destinations: IBackupDestinationRepository,
        audit: IAuditLog,
        notifier: INotifier,
        admins: IAdminDirectory,
        uow: IUnitOfWork,
        options: UpdateOptions,
    ) -> UpdateService:
        return UpdateService(
            runs, repo, source, backup, backup_runs, destinations, audit, notifier, admins, uow, options
        )

    @provide
    def get_admin(self, service: UpdateService) -> UpdateAdmin:
        return UpdateAdmin(service)
