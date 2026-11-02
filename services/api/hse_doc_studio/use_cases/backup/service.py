"""Выполнение бэкапа: запуск, части, манифест, хранение, уведомления. Один экземпляр на процесс."""

from __future__ import annotations

import asyncio
import secrets
from datetime import datetime
from uuid import uuid4

import structlog

from hse_doc_studio.core.backup.crypto import new_salt
from hse_doc_studio.core.backup.destinations import object_key
from hse_doc_studio.core.backup.entities import (
    MANIFEST_FORMAT,
    MANIFEST_NAME,
    BackupRun,
    BackupSettings,
    DestinationSecrets,
    Manifest,
    ManifestPart,
    RunStatus,
    RunTrigger,
    StoredBackup,
    StoredDestination,
)
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.keys import make_key
from hse_doc_studio.core.backup.manifest import dump_manifest, is_backup_id, manifest_sha256, parse_manifest
from hse_doc_studio.core.backup.protocols import (
    IAdminDirectory,
    IBackupDestinationRepository,
    IBackupEnvironment,
    IBackupKeySource,
    IBackupPlanFactory,
    IBackupRunRepository,
    IBackupStoreFactory,
    IPartUploader,
)
from hse_doc_studio.core.backup.retention import select_expired
from hse_doc_studio.core.backup.settings import settings_from
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.storage.errors import ObjectNotFoundError
from hse_doc_studio.core.storage.ports import IObjectStore

logger = structlog.get_logger()

ERROR_MAX = 500
DEST_TABLE = "backup_destinations"
KEY_COLUMN = "access_key_enc"
SECRET_COLUMN = "secret_key_enc"  # noqa: S105 — имя колонки, не секрет


def new_backup_id(now: datetime) -> str:
    return f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}"


def short_error(exc: BaseException) -> str:
    text = str(exc).strip() or type(exc).__name__
    return text[:ERROR_MAX]


class BackupService:
    def __init__(
        self,
        destinations: IBackupDestinationRepository,
        runs: IBackupRunRepository,
        settings_repo: IInstanceSettingsRepository,
        stores: IBackupStoreFactory,
        uploader: IPartUploader,
        plans: IBackupPlanFactory,
        env: IBackupEnvironment,
        key_source: IBackupKeySource,
        cipher: ISecretCipher,
        audit: IAuditLog,
        notifier: INotifier,
        admins: IAdminDirectory,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._destinations = destinations
        self._runs = runs
        self._settings = settings_repo
        self._stores = stores
        self._uploader = uploader
        self._plans = plans
        self._env = env
        self._keys = key_source
        self._cipher = cipher
        self._audit = audit
        self._notifier = notifier
        self._admins = admins
        self._clock = clock
        self._tasks: set[asyncio.Task[None]] = set()

    # ---- ключи назначения ----

    def open_secrets(self, stored: StoredDestination) -> DestinationSecrets:
        dest_id = stored.destination.id
        try:
            access = (
                self._cipher.decrypt(stored.access_key_enc, aad=column_aad(DEST_TABLE, KEY_COLUMN, dest_id)).reveal()
                if stored.access_key_enc
                else None
            )
            secret = (
                self._cipher.decrypt(stored.secret_key_enc, aad=column_aad(DEST_TABLE, SECRET_COLUMN, dest_id)).reveal()
                if stored.secret_key_enc
                else None
            )
        except GitSyncError as exc:
            raise BackupError(
                BackupErrorCode.secrets_unavailable,
                "the saved destination keys cannot be decrypted: SECRETS_KEY does not match, enter the keys again",
            ) from exc
        return DestinationSecrets(access_key=access, secret_key=secret)

    def open_store(self, stored: StoredDestination) -> IObjectStore:
        return self._stores.open(stored.destination.spec, self.open_secrets(stored))

    # ---- запуск ----

    async def recover_stale(self) -> int:
        """Запуски `running` от прошлого процесса не имеют владельца: помечаются прерванными."""
        return await self._runs.interrupt_running(self._clock())

    async def start(self, *, trigger: RunTrigger, destination_id: str | None, actor_id: str | None) -> BackupRun:
        stored = (
            await self._destinations.get(destination_id) if destination_id else await self._destinations.get_default()
        )
        if stored is None:
            code = BackupErrorCode.not_found if destination_id else BackupErrorCode.no_destination
            raise BackupError(code, "backup destination is not found" if destination_id else "no backup destination")
        now = self._clock()
        run = BackupRun(
            id=str(uuid4()),
            destination_id=stored.destination.id,
            destination_name=stored.destination.spec.name,
            trigger=trigger,
            status=RunStatus.running,
            stage="starting",
            started_at=now,
            started_by=actor_id,
        )
        if not await self._runs.start(run):
            raise BackupError(BackupErrorCode.already_running, "another backup is already running")
        await self._audit.record(
            "backup.run_start",
            actor_id=actor_id,
            target=run.id,
            details={"trigger": trigger.value, "destination": run.destination_name},
        )
        task = asyncio.create_task(self._execute(run, stored))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return run

    async def run_and_wait(self, *, trigger: RunTrigger, destination_id: str | None, actor_id: str | None) -> BackupRun:
        run = await self.start(trigger=trigger, destination_id=destination_id, actor_id=actor_id)
        await self.drain()
        finished = await self._runs.get(run.id)
        return finished or run

    async def drain(self) -> None:
        """Дожидается начатых запусков (остановка процесса и тесты)."""
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def cancel_all(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await self.drain()

    async def _execute(self, run: BackupRun, stored: StoredDestination) -> None:
        settings = settings_from(await self._settings.get_all())
        backup_id: str | None = None
        store: IObjectStore | None = None
        base = ""
        try:
            store = self.open_store(stored)
            now = self._clock()
            backup_id = new_backup_id(now)
            base = object_key(stored.destination.spec.prefix, backup_id)
            salt = new_salt()
            installation = await self._keys.installation_keys()
            passphrase = await self._keys.passphrase()
            key = await asyncio.to_thread(
                make_key,
                settings.encryption_mode,
                salt,
                installation_key=installation[0] if installation else None,
                passphrase=passphrase,
            )
            plan = await self._plans.create()
            parts: list[ManifestPart] = []
            notes: dict[str, int | str] = {}
            for producer in plan.producers:
                await self._runs.set_stage(run.id, producer.name)
                part, part_notes = await self._uploader.upload(store, base, producer, key.key)
                parts.append(part)
                notes.update({f"{producer.name}.{name}": value for name, value in part_notes.items()})
            await self._runs.set_stage(run.id, "manifest")
            manifest = Manifest(
                format=MANIFEST_FORMAT,
                backup_id=backup_id,
                created_at=now,
                app_version=self._env.app_version,
                schema_revision=await self._env.schema_revision(),
                installation_id=await self._env.installation_id(),
                encryption_mode=settings.encryption_mode,
                salt_hex=salt.hex(),
                key_check=key.check,
                key_fingerprint=key.fingerprint,
                parts=tuple(parts),
                notes=notes,
            )
            data = dump_manifest(manifest)
            await store.put(object_key(base, MANIFEST_NAME), data, content_type="application/json")
            await self._finish(
                run,
                RunStatus.ok,
                size=manifest.total_size,
                backup_id=backup_id,
                error=None,
                manifest_sha=manifest_sha256(data),
            )
        except asyncio.CancelledError:
            await asyncio.shield(self._cleanup(store, base))
            await asyncio.shield(
                self._finish(run, RunStatus.interrupted, size=None, backup_id=None, error="stopped", manifest_sha=None)
            )
            raise
        except Exception as exc:
            logger.warning("backup failed", run_id=run.id, error=short_error(exc))
            await self._cleanup(store, base)
            finished = await self._finish(
                run, RunStatus.failed, size=None, backup_id=None, error=short_error(exc), manifest_sha=None
            )
            await self._notify_failed(finished, settings)
            return
        await self._retain(stored, store, settings)

    async def _finish(
        self,
        run: BackupRun,
        status: RunStatus,
        *,
        size: int | None,
        backup_id: str | None,
        error: str | None,
        manifest_sha: str | None,
    ) -> BackupRun:
        finished = await self._runs.finish(
            run.id,
            status=status,
            at=self._clock(),
            size_bytes=size,
            backup_id=backup_id,
            error=error,
            manifest_sha256=manifest_sha,
        )
        await self._audit.record(
            "backup.run_finish",
            actor_id=run.started_by,
            target=run.id,
            details={
                "status": status.value,
                "trigger": run.trigger.value,
                "destination": run.destination_name,
                "size_bytes": size,
                "duration_s": finished.duration_s,
                "error": error,
            },
        )
        return finished

    async def _cleanup(self, store: IObjectStore | None, base: str) -> None:
        """Недописанный бэкап (нет манифеста) убирается: полу-бэкап в хранилище только вводит в заблуждение."""
        if store is None or not base:
            return
        try:
            for info in await store.list_objects(base + "/"):
                await store.delete(info.key)
        except Exception:
            logger.warning("backup cleanup failed", prefix=base, exc_info=True)

    async def _notify_failed(self, run: BackupRun, settings: BackupSettings) -> None:
        if not settings.notify_admins:
            return
        payload = NotificationPayload(path=run.destination_name, excerpt=(run.error or "")[:200], ref_id=run.id)
        try:
            for admin_id in await self._admins.active_admin_ids():
                await self._notifier.notify(
                    admin_id, NotificationKind.backup_failed, payload, dedupe_key=f"bkf:{run.id}"
                )
        except Exception:
            logger.warning("backup failure notification failed", run_id=run.id, exc_info=True)

    # ---- хранение ----

    async def _retain(self, stored: StoredDestination, store: IObjectStore, settings: BackupSettings) -> None:
        try:
            alive = await self._runs.alive_for(stored.destination.id)
            for run in select_expired(
                alive, keep_last=settings.keep_last, keep_days=settings.keep_days, now=self._clock()
            ):
                await self.delete_stored(stored, store, run)
        except Exception:
            logger.warning("backup retention failed", destination=stored.destination.id, exc_info=True)

    async def delete_stored(self, stored: StoredDestination, store: IObjectStore, run: BackupRun) -> None:
        """Снимает бэкап запуска из хранилища: части, потом манифест; затем метка в истории."""
        if not run.backup_id or not is_backup_id(run.backup_id):
            return
        base = object_key(stored.destination.spec.prefix, run.backup_id)
        await delete_backup_objects(store, base)
        await self._runs.mark_removed(run.id, self._clock())
        await self._audit.record(
            "backup.delete", actor_id=None, target=run.id, details={"backup_id": run.backup_id, "reason": "retention"}
        )

    # ---- чтение хранилища ----

    async def list_stored(self, stored: StoredDestination) -> list[StoredBackup]:
        return await list_backups(self.open_store(stored), stored.destination.spec.prefix)


async def delete_backup_objects(store: IObjectStore, base: str) -> None:
    infos = await store.list_objects(base + "/")
    manifest_key = object_key(base, MANIFEST_NAME)
    for info in infos:
        if info.key != manifest_key:
            await store.delete(info.key)
    await store.delete(manifest_key)


async def list_backups(store: IObjectStore, prefix: str) -> list[StoredBackup]:
    """Бэкапы по манифестам в `prefix`, новые первыми; нечитаемые манифесты пропускаются."""
    root = (prefix.strip("/") + "/") if prefix.strip("/") else ""
    found: list[StoredBackup] = []
    for info in await store.list_objects(root):
        rest = info.key[len(root) :]
        folder, _, name = rest.partition("/")
        if name != MANIFEST_NAME or not is_backup_id(folder):
            continue
        try:
            data = await store.get(info.key)
            found.append(StoredBackup(folder, parse_manifest(data), manifest_sha256(data)))
        except (BackupError, ObjectNotFoundError):
            logger.warning("backup manifest unreadable", key=info.key)
    return sorted(found, key=lambda item: item.manifest.created_at, reverse=True)
