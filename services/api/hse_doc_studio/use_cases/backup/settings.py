"""Настройки бэкапов: расписание, хранение, шифрование, парольная фраза."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.backup.entities import BackupRun, BackupSettings, EncryptionMode
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.protocols import IBackupRunRepository
from hse_doc_studio.core.backup.schedule import next_run
from hse_doc_studio.core.backup.settings import (
    KEY_LAST_SCHEDULED,
    KEY_PASSPHRASE,
    last_scheduled_from,
    settings_from,
    settings_to,
    validate_settings,
)
from hse_doc_studio.core.git_sync.protocols import ISecretCipher
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.secrets import column_aad
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN

MIN_PASSPHRASE = 12
SECRET_TABLE = "instance_settings"  # noqa: S105 — имя таблицы, не пароль
SECRET_COLUMN = "secret_enc"  # noqa: S105 — имя колонки, не пароль


@dataclass(frozen=True)
class BackupStatus:
    settings: BackupSettings
    passphrase_set: bool
    next_run_at: datetime | None
    last_scheduled_at: datetime | None
    running: BackupRun | None
    last_run: BackupRun | None


async def load_status(repo: IInstanceSettingsRepository, runs: IBackupRunRepository, now: datetime) -> BackupStatus:
    values = await repo.get_all()
    settings = settings_from(values)
    last = last_scheduled_from(values)
    upcoming = next_run(settings.schedule, last, now) if settings.enabled else None
    return BackupStatus(
        settings=settings,
        passphrase_set=bool(values.get(KEY_PASSPHRASE)),
        next_run_at=upcoming,
        last_scheduled_at=last,
        running=await runs.running(),
        last_run=await runs.last_finished(),
    )


class GetBackupSettingsUC:
    def __init__(self, repo: IInstanceSettingsRepository, runs: IBackupRunRepository, clock: Clock = utc_now) -> None:
        self._repo = repo
        self._runs = runs
        self._clock = clock

    async def execute(self, actor: Actor) -> BackupStatus:
        require_admin(actor)
        return await load_status(self._repo, self._runs, self._clock())


def _check_passphrase(new: BackupSettings, passphrase: str | None, *, have_phrase: bool) -> None:
    if passphrase is not None and len(passphrase) < MIN_PASSPHRASE:
        raise BackupError(BackupErrorCode.invalid_input, "passphrase is too short (12+ characters)", field="passphrase")
    if new.encryption_mode is EncryptionMode.passphrase and not (have_phrase or passphrase):
        raise BackupError(BackupErrorCode.invalid_input, "set a passphrase for this mode", field="passphrase")


class UpdateBackupSettingsUC:
    def __init__(
        self,
        repo: IInstanceSettingsRepository,
        runs: IBackupRunRepository,
        cipher: ISecretCipher,
        audit: IAuditLog,
        uow: IUnitOfWork,
        clock: Clock = utc_now,
    ) -> None:
        self._repo = repo
        self._runs = runs
        self._cipher = cipher
        self._audit = audit
        self._uow = uow
        self._clock = clock

    async def execute(self, actor: Actor, new: BackupSettings, *, passphrase: str | None = None) -> BackupStatus:
        """Полная замена настроек. `passphrase=None` оставляет фразу как есть; в режиме `passphrase` она обязательна."""
        admin_id = require_admin(actor)
        validate_settings(new)
        values = await self._repo.get_all()
        before = settings_from(values)
        _check_passphrase(new, passphrase, have_phrase=bool(values.get(KEY_PASSPHRASE)))
        now = self._clock()
        async with self._uow.begin():
            for key, value in settings_to(new).items():
                await self._repo.set(key, value, source=SOURCE_ADMIN)
            if passphrase is not None:
                sealed = self._cipher.encrypt(
                    Secret(passphrase), aad=column_aad(SECRET_TABLE, SECRET_COLUMN, KEY_PASSPHRASE)
                )
                await self._repo.set_secret(KEY_PASSPHRASE, sealed, source=SOURCE_ADMIN)
            if new.enabled and not before.enabled and new.schedule.kind.value == "cron":
                # Включение по cron ждёт ближайшего срабатывания, а не стартует сразу.
                await self._repo.set(KEY_LAST_SCHEDULED, now.isoformat(), source="system")
            if not new.enabled and before.enabled:
                await self._repo.delete(KEY_LAST_SCHEDULED)
            if settings_to(before) != settings_to(new) or passphrase is not None:
                await self._audit.record(
                    "backup.settings_update",
                    actor_id=admin_id,
                    details={
                        "before": settings_to(before),
                        "after": settings_to(new),
                        "passphrase_changed": passphrase is not None,
                    },
                )
        return await load_status(self._repo, self._runs, now)
