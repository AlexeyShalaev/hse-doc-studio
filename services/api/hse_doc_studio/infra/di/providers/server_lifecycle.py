"""Провайдеры жизненного цикла данных: реестр источников, движок очистки, контроль места."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.lifecycle.disk import PROCESS_SAFE_MODE, SafeMode
from hse_doc_studio.core.lifecycle.policies import POLICIES
from hse_doc_studio.core.lifecycle.ports import IAdminDirectory, ILifecycleRuns, ILifecycleSource, IStorageProbe
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.repositories.lifecycle_admins import SqlAdminDirectory
from hse_doc_studio.infra.db.repositories.lifecycle_runs import SqlLifecycleRuns
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.jobs.retention import JobRetention
from hse_doc_studio.infra.lifecycle.files import CollabStateSource
from hse_doc_studio.infra.lifecycle.job_source import JobsSource
from hse_doc_studio.infra.lifecycle.probe import StorageProbe
from hse_doc_studio.infra.lifecycle.sql_sources import DeleteBatchesSource, PartitionedTableSource, TableMeasure
from hse_doc_studio.use_cases.lifecycle.admin import (
    GetLifecycleUC,
    RunLifecycleUC,
    TaskRun,
    UpdateRetentionUC,
    UpdateThresholdsUC,
)
from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine
from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard

_AUDIT_BATCH = "SELECT audit_log_purge_batch(:cutoff, :n)"


def _batch(table: str, condition: str, order: str = "") -> str:
    """Пачка удаления по готовому условию: имена таблиц и условия только из констант этого модуля."""
    return f"DELETE FROM {table} WHERE id IN (SELECT id FROM {table} WHERE {condition}{order} LIMIT :n)"  # noqa: S608


_AI_USAGE_BATCH = _batch("ai_usage", "at < :cutoff", " ORDER BY at")
_NOTIFICATIONS = (_batch("notifications", "created_at < :cutoff"),)
_COLLAB_REQUESTS = (
    _batch("project_invitations", "expires_at < :cutoff"),
    _batch("access_requests", "status <> 'pending' AND created_at < :cutoff"),
    _batch("project_transfers", "expires_at < :cutoff"),
)
_SHARE_LINKS = (_batch("share_links", "revoked_at < :cutoff OR expires_at < :cutoff"),)
_GUEST_SESSIONS = (_batch("guest_sessions", "expires_at < :cutoff"),)
# Гостевая сессия после истечения нужна ещё неделю разве что для разбора спорного входа: дальше она мусор.
_GUEST_GRACE = timedelta(days=7)


class TaskStatsHolder:
    """Итоги собственных периодических задач: раннер фоновых задач подключает чтение при старте приложения."""

    def __init__(self) -> None:
        self.reader: Callable[[], dict[str, TaskRun]] = dict


class ServerLifecycleProvider(Provider):
    scope = Scope.APP

    @provide
    def get_safe_mode(self) -> SafeMode:
        return PROCESS_SAFE_MODE

    @provide
    def get_task_stats(self) -> TaskStatsHolder:
        return TaskStatsHolder()

    @provide
    def get_runs(self, sessions: SessionProvider) -> ILifecycleRuns:
        return SqlLifecycleRuns(sessions)

    @provide
    def get_admins(self, sessions: SessionProvider) -> IAdminDirectory:
        return SqlAdminDirectory(sessions)

    @provide
    def get_probe(self, sessions: SessionProvider) -> IStorageProbe:
        data = settings.data_dir.expanduser()
        projects = settings.server.projects_root or data / "projects"
        objects = settings.s3.fs_root or data / "objects"
        paths: list[tuple[str, Path]] = [("data", data), ("projects", projects.expanduser())]
        if settings.s3.bucket is None:
            paths.append(("objects", objects.expanduser()))
        return StorageProbe(sessions, paths, db_size_limit_bytes=settings.lifecycle.db_size_limit_bytes)

    @provide
    def get_engine(
        self,
        sessions: SessionProvider,
        retention: JobRetention,
        instance_settings: IInstanceSettingsRepository,
        runs: ILifecycleRuns,
        audit: IAuditLog,
    ) -> LifecycleEngine:
        cfg = settings.lifecycle
        pause = cfg.batch_pause_s
        sources: dict[str, ILifecycleSource] = {
            "audit_log": PartitionedTableSource(
                sessions,
                "audit_log",
                "audit_log",
                months_ahead=cfg.partition_months_ahead,
                pause_s=pause,
                batch_delete=_AUDIT_BATCH,
                batch_returns_count=True,
            ),
            "ai_usage": PartitionedTableSource(
                sessions,
                "ai_usage",
                "ai_usage",
                months_ahead=cfg.partition_months_ahead,
                pause_s=pause,
                batch_delete=_AI_USAGE_BATCH,
            ),
            "jobs": JobsSource(retention, TableMeasure(sessions, "jobs", ("jobs",))),
            "notifications": DeleteBatchesSource(
                sessions, "notifications", ("notifications",), _NOTIFICATIONS, pause_s=pause
            ),
            "collab_requests": DeleteBatchesSource(
                sessions,
                "collab_requests",
                ("project_invitations", "access_requests", "project_transfers"),
                _COLLAB_REQUESTS,
                pause_s=pause,
            ),
            "share_links": DeleteBatchesSource(
                sessions,
                "share_links",
                ("share_links", "share_link_visits", "share_link_grants"),
                _SHARE_LINKS,
                pause_s=pause,
            ),
            "guest_sessions": DeleteBatchesSource(
                sessions,
                "guest_sessions",
                ("guest_sessions", "guest_session_links"),
                _GUEST_SESSIONS,
                pause_s=pause,
                fixed_age=_GUEST_GRACE,
            ),
            "collab_state": CollabStateSource(settings.data_dir.expanduser() / "collab"),
        }
        # Остальным источникам реестра достаточно размера таблиц: их чистит собственная задача или предел при записи.
        for policy in POLICIES:
            if policy.key not in sources and policy.tables:
                sources[policy.key] = TableMeasure(sessions, policy.key, policy.tables)
        return LifecycleEngine(
            sources,
            instance_settings,
            runs,
            audit,
            env_days={
                "audit_log": settings.server.audit_retention_days,
                "ai_usage": settings.ai_gateway.usage_retention_days,
                "jobs": settings.server.job_retention_days,
            },
            batch_size=cfg.batch_size,
            budget_s=cfg.run_budget_s,
        )

    @provide
    def get_guard(
        self,
        probe: IStorageProbe,
        instance_settings: IInstanceSettingsRepository,
        notifier: INotifier,
        admins: IAdminDirectory,
        safe_mode: SafeMode,
    ) -> StorageGuard:
        return StorageGuard(
            probe,
            instance_settings,
            notifier,
            admins,
            safe_mode,
            safe_mode_enabled=settings.lifecycle.safe_mode_enabled,
        )

    @provide
    def get_overview_uc(
        self,
        engine: LifecycleEngine,
        instance_settings: IInstanceSettingsRepository,
        runs: ILifecycleRuns,
        guard: StorageGuard,
        safe_mode: SafeMode,
        holder: TaskStatsHolder,
    ) -> GetLifecycleUC:
        return GetLifecycleUC(engine, instance_settings, runs, guard, safe_mode, lambda: holder.reader())  # noqa: PLW0108 — reader подменяется при старте

    @provide
    def get_update_retention_uc(
        self, instance_settings: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> UpdateRetentionUC:
        return UpdateRetentionUC(instance_settings, audit, uow)

    @provide
    def get_update_thresholds_uc(
        self, instance_settings: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork
    ) -> UpdateThresholdsUC:
        return UpdateThresholdsUC(instance_settings, audit, uow)

    @provide
    def get_run_uc(self, engine: LifecycleEngine, audit: IAuditLog) -> RunLifecycleUC:
        return RunLifecycleUC(engine, audit)
