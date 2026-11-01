"""Восстановление из админки: предпросмотр (сухой прогон), подтверждение, запись в режиме обслуживания.

Одно задание за раз, состояние в памяти процесса. Порядок и причины: docs/design/backups.md, раздел 5.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.backup.destinations import object_key
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.manifest import is_backup_id
from hse_doc_studio.core.backup.protocols import (
    IBackupDestinationRepository,
    IBackupKeySource,
    IBackupRunRepository,
    IMaintenanceMode,
    IPartFetcher,
    IRestoreTargetFactory,
    TargetState,
)
from hse_doc_studio.core.backup.restore_job import RestoreJob, RestorePhase
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.backup.restore import BackupSource, RestoreBackupUC
from hse_doc_studio.use_cases.backup.service import BackupService, short_error

logger = structlog.get_logger()

RESTART_DELAY_S = 3.0
OTHERS_WAIT_S = 30.0
OTHERS_POLL_S = 1.0
INTERNAL_CODE = "backup_restore_failed"


class RestoreCoordinator:
    def __init__(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        service: BackupService,
        keys: IBackupKeySource,
        targets: IRestoreTargetFactory,
        fetcher: IPartFetcher,
        maintenance: IMaintenanceMode,
        audit: IAuditLog,
        *,
        clock: Clock = utc_now,
        others_wait_s: float = OTHERS_WAIT_S,
        others_poll_s: float = OTHERS_POLL_S,
        restart_delay_s: float = RESTART_DELAY_S,
        apply_allowed: bool = True,
    ) -> None:
        self._apply_allowed = apply_allowed
        self._destinations = destinations
        self._runs = runs
        self._service = service
        self._keys = keys
        self._targets = targets
        self._fetcher = fetcher
        self._maintenance = maintenance
        self._audit = audit
        self._clock = clock
        self._others_wait_s = others_wait_s
        self._others_poll_s = others_poll_s
        self._restart_delay_s = restart_delay_s
        self._job: RestoreJob | None = None
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    # ---- чтение ----

    def current(self, actor: Actor) -> RestoreJob | None:
        require_admin(actor)
        return self._job

    @property
    def busy(self) -> bool:
        return self._task is not None and not self._task.done()

    async def drain(self) -> None:
        if self._task is not None:
            await asyncio.gather(self._task, return_exceptions=True)

    # ---- предпросмотр ----

    async def preview(self, actor: Actor, destination_id: str, backup_id: str) -> RestoreJob:
        admin_id = require_admin(actor)
        async with self._lock:
            if self.busy or self._maintenance.active:
                raise BackupError(BackupErrorCode.restore_busy, "a restore is already in progress")
            stored = await self._destinations.get(destination_id)
            if stored is None or not is_backup_id(backup_id):
                raise BackupError(BackupErrorCode.not_found, "backup not found")
            job = RestoreJob(
                id=str(uuid4()),
                destination_id=destination_id,
                destination_name=stored.destination.spec.name,
                backup_id=backup_id,
                started_at=self._clock(),
            )
            self._job = job
            self._publish(job)
            await self._audit.record(
                "backup.restore_preview",
                actor_id=admin_id,
                target=destination_id,
                details={"backup_id": backup_id},
            )
            self._task = asyncio.create_task(self._preview(job))
            return job

    async def _preview(self, job: RestoreJob) -> None:
        session = None
        try:
            stored = await self._destinations.get(job.destination_id)
            if stored is None:
                raise BackupError(BackupErrorCode.not_found, "destination not found")
            source = BackupSource(
                self._service.open_store(stored), object_key(stored.destination.spec.prefix, job.backup_id)
            )
            session = await self._targets.open()
            uc = RestoreBackupUC(session, self._fetcher)
            verified = await uc.load(
                source, installation_keys=await self._keys.installation_keys(), passphrase=await self._keys.passphrase()
            )
            job.manifest = verified.manifest
            result = await uc.execute(
                source, verified, apply=False, overwrite=False, confirm=lambda _s: False, report=job.say
            )
            job.target = result.state
            job.phase = RestorePhase.verified
        except Exception as exc:
            self._fail(job, exc)
        finally:
            if session is not None:
                await session.close()
            job.finished_at = self._clock()
            self._publish(job)

    # ---- запись ----

    async def apply(self, actor: Actor, job_id: str, *, overwrite: bool, confirm: str) -> RestoreJob:
        admin_id = require_admin(actor)
        if not self._apply_allowed:
            raise BackupError(BackupErrorCode.unsupported, "restore from the admin panel is disabled: use the CLI")
        async with self._lock:
            job = self._job
            if job is None or job.id != job_id:
                raise BackupError(BackupErrorCode.not_found, "restore job not found")
            if self.busy:
                raise BackupError(BackupErrorCode.restore_busy, "the restore is still running")
            await self._check_apply(job, overwrite=overwrite, confirm=confirm)
            job.overwrite = overwrite
            job.phase = RestorePhase.applying
            job.error = job.error_code = None
            job.finished_at = None
            job.say("--- запись ---")
            self._publish(job)
            await self._audit.record(
                "backup.restore_start",
                actor_id=admin_id,
                target=job.destination_id,
                details={"backup_id": job.backup_id, "overwrite": overwrite},
            )
            self._task = asyncio.create_task(self._apply(job, admin_id))
            return job

    async def _check_apply(self, job: RestoreJob, *, overwrite: bool, confirm: str) -> None:
        retry = job.phase is RestorePhase.failed and job.wrote
        if job.phase is not RestorePhase.verified and not retry:
            raise BackupError(BackupErrorCode.invalid_input, "run the preview first")
        if confirm.strip() != job.backup_id:
            raise BackupError(BackupErrorCode.restore_unconfirmed, "type the backup id to confirm", field="confirm")
        if job.requires_overwrite and not overwrite:
            raise BackupError(
                BackupErrorCode.unsafe_target,
                "the target installation is not empty; the restore would destroy its data: confirm the overwrite",
                field="overwrite",
            )
        if await self._runs.running() is not None:
            raise BackupError(BackupErrorCode.restore_busy, "a backup is running: wait for it to finish")

    async def _apply(self, job: RestoreJob, admin_id: str) -> None:
        session = None
        try:
            if not self._maintenance.active:
                await self._maintenance.enter(reason=f"restore {job.backup_id}")
            stored = await self._destinations.get(job.destination_id)
            if stored is None:
                raise BackupError(BackupErrorCode.not_found, "destination not found")
            source = BackupSource(
                self._service.open_store(stored), object_key(stored.destination.spec.prefix, job.backup_id)
            )
            session = await self._targets.open()
            await self._wait_for_others(session, job)
            uc = RestoreBackupUC(session, self._fetcher)
            verified = await uc.load(
                source, installation_keys=await self._keys.installation_keys(), passphrase=await self._keys.passphrase()
            )
            await uc.execute(
                source,
                verified,
                apply=True,
                overwrite=job.overwrite,
                confirm=lambda _s: True,  # подтверждение уже получено формой: id бэкапа и флаг перезаписи
                report=job.say,
                before_write=lambda: setattr(job, "wrote", True),
            )
            job.phase = RestorePhase.done
            job.finished_at = self._clock()
            job.restarting = self._maintenance.request_restart(delay_s=self._restart_delay_s)
        except Exception as exc:
            self._fail(job, exc)
            if not job.wrote:
                # Ничего не записано: установка цела, возвращаем её в работу.
                await self._leave_quietly()
        finally:
            if session is not None:
                await session.close()
            job.finished_at = job.finished_at or self._clock()
            self._publish(job)
        await self._record_finish(job, admin_id)

    async def _wait_for_others(self, session: object, job: RestoreJob) -> None:
        """Соединения api и ручек, начатых до включения режима, закрываются сами; ждём их, а не отказываем сразу."""
        waited = 0.0
        while await session.api_is_running():  # type: ignore[attr-defined]
            if waited >= self._others_wait_s:
                return  # execute сам откажет с понятным текстом
            if waited == 0:
                job.say("жду, пока закроются прочие соединения с базой")
            await asyncio.sleep(self._others_poll_s)
            waited += self._others_poll_s

    async def _record_finish(self, job: RestoreJob, admin_id: str) -> None:
        try:
            await self._audit.record(
                "backup.restore_finish",
                actor_id=admin_id,
                target=job.destination_id,
                details={
                    "backup_id": job.backup_id,
                    "result": job.phase.value,
                    "error_code": job.error_code,
                    "wrote": job.wrote,
                },
            )
        except Exception:
            # База могла быть заменена или недоступна; результат остаётся в задании и в журнале процесса.
            logger.warning("restore audit not written", backup_id=job.backup_id, exc_info=True)

    # ---- отмена ----

    async def cancel(self, actor: Actor) -> None:
        """Снимает задание и выходит из режима обслуживания (после предпросмотра или неудачной записи)."""
        admin_id = require_admin(actor)
        async with self._lock:
            job = self._job
            if job is None:
                return
            if self.busy:
                raise BackupError(BackupErrorCode.restore_busy, "the restore is still running")
            if job.phase is RestorePhase.done:
                raise BackupError(BackupErrorCode.restore_busy, "the restore is finished: the service is restarting")
            if self._maintenance.active:
                await self._maintenance.leave()
            self._job = None
            self._maintenance.publish({})
            await self._audit.record(
                "backup.restore_cancel",
                actor_id=admin_id,
                target=job.destination_id,
                details={"backup_id": job.backup_id, "wrote": job.wrote},
            )

    # ---- служебное ----

    async def _leave_quietly(self) -> None:
        try:
            await self._maintenance.leave()
        except Exception:
            logger.warning("maintenance mode was not left", exc_info=True)

    def _fail(self, job: RestoreJob, exc: Exception) -> None:
        if isinstance(exc, BackupError):
            job.error_code, job.error = exc.code.value, exc.message
        else:
            logger.warning("restore failed", backup_id=job.backup_id, exc_info=True)
            job.error_code, job.error = INTERNAL_CODE, short_error(exc)
        job.phase = RestorePhase.failed
        job.say(f"ошибка: {job.error}")

    def _publish(self, job: RestoreJob) -> None:
        self._maintenance.publish(
            {
                "phase": job.phase.value,
                "error_code": job.error_code,
                "wrote": job.wrote,
                "restarting": job.restarting,
                "backup_id": job.backup_id,
            }
        )


def describe_target(state: TargetState | None) -> dict[str, int] | None:
    return None if state is None else {"users": state.users, "projects": state.projects, "objects": state.objects}
