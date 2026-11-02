"""Запуски, список бэкапов в хранилище, удаление бэкапа, плановый тик."""

from __future__ import annotations

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.backup.destinations import object_key
from hse_doc_studio.core.backup.entities import BackupRun, RunTrigger, StoredBackup
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.manifest import is_backup_id
from hse_doc_studio.core.backup.protocols import IBackupDestinationRepository, IBackupRunRepository
from hse_doc_studio.core.backup.schedule import is_due
from hse_doc_studio.core.backup.settings import KEY_LAST_SCHEDULED, last_scheduled_from, settings_from
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.listing import Found, Window, clamp_limit
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.backup.service import BackupService, delete_backup_objects

logger = structlog.get_logger()


class StartBackupUC:
    def __init__(self, service: BackupService) -> None:
        self._service = service

    async def execute(self, actor: Actor, destination_id: str | None) -> BackupRun:
        admin_id = require_admin(actor)
        return await self._service.start(trigger=RunTrigger.manual, destination_id=destination_id, actor_id=admin_id)


class ListRunsUC:
    def __init__(self, runs: IBackupRunRepository) -> None:
        self._runs = runs

    async def execute(self, actor: Actor, window: Window) -> Found[BackupRun]:
        require_admin(actor)
        return await self._runs.page(Window(limit=clamp_limit(window.limit), offset=max(0, window.offset)))


class GetRunUC:
    def __init__(self, runs: IBackupRunRepository) -> None:
        self._runs = runs

    async def execute(self, actor: Actor, run_id: str) -> BackupRun:
        require_admin(actor)
        run = await self._runs.get(run_id)
        if run is None:
            raise BackupError(BackupErrorCode.not_found, "run not found")
        return run


class ListStoredBackupsUC:
    def __init__(self, destinations: IBackupDestinationRepository, service: BackupService) -> None:
        self._destinations = destinations
        self._service = service

    async def execute(self, actor: Actor, destination_id: str) -> list[StoredBackup]:
        require_admin(actor)
        stored = await self._destinations.get(destination_id)
        if stored is None:
            raise BackupError(BackupErrorCode.not_found, "destination not found")
        return await self._service.list_stored(stored)


class DeleteStoredBackupUC:
    def __init__(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        service: BackupService,
        audit: IAuditLog,
    ) -> None:
        self._destinations = destinations
        self._runs = runs
        self._service = service
        self._audit = audit

    async def execute(self, actor: Actor, destination_id: str, backup_id: str) -> None:
        admin_id = require_admin(actor)
        stored = await self._destinations.get(destination_id)
        if stored is None or not is_backup_id(backup_id):
            raise BackupError(BackupErrorCode.not_found, "backup not found")
        running = await self._runs.running()
        if running is not None and running.destination_id == destination_id:
            raise BackupError(BackupErrorCode.conflict, "a backup to this destination is running")
        store = self._service.open_store(stored)
        await delete_backup_objects(store, object_key(stored.destination.spec.prefix, backup_id))
        for run in await self._runs.alive_for(destination_id):
            if run.backup_id == backup_id:
                await self._runs.mark_removed(run.id, run.finished_at or run.started_at)
        await self._audit.record(
            "backup.delete",
            actor_id=admin_id,
            target=destination_id,
            details={"backup_id": backup_id, "reason": "manual"},
        )


class ScheduledBackupTick:
    """Один проход планировщика: пора ли, и если да, запуск в назначение по умолчанию."""

    def __init__(
        self,
        repo: IInstanceSettingsRepository,
        service: BackupService,
        destinations: IBackupDestinationRepository,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._repo = repo
        self._service = service
        self._destinations = destinations
        self._clock = clock

    async def run_once(self) -> BackupRun | None:
        values = await self._repo.get_all()
        settings = settings_from(values)
        if not settings.enabled:
            return None
        now = self._clock()
        if not is_due(settings.schedule, last_scheduled_from(values), now):
            return None
        # Метка до старта: сбойный запуск ждёт следующего срабатывания, а не повторяется каждый тик.
        await self._repo.set(KEY_LAST_SCHEDULED, now.isoformat(), source="system")
        if await self._destinations.get_default() is None:
            logger.warning("scheduled backup skipped: no destination")
            return None
        try:
            return await self._service.start(trigger=RunTrigger.schedule, destination_id=None, actor_id=None)
        except BackupError as exc:
            logger.warning("scheduled backup not started", code=exc.code.value)
            return None
