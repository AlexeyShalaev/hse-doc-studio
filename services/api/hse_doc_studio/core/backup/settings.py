"""Настройки бэкапов в `instance_settings`: ключи с префиксом `backup.`. Испорченное значение читается как умолчание."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hse_doc_studio.core.backup.entities import BackupSettings, EncryptionMode
from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode
from hse_doc_studio.core.backup.schedule import Schedule, ScheduleKind

KEY_PREFIX = "backup."
KEY_LAST_SCHEDULED = KEY_PREFIX + "last_scheduled_at"
KEY_PASSPHRASE = KEY_PREFIX + "passphrase"  # noqa: S105 — имя ключа настроек, не пароль
MAX_KEEP = 10_000


def _int(values: Mapping[str, object], name: str, default: int) -> int:
    raw = values.get(KEY_PREFIX + name)
    return raw if isinstance(raw, int) and not isinstance(raw, bool) else default


def settings_from(values: Mapping[str, object]) -> BackupSettings:
    base = BackupSettings()
    kind_raw = values.get(KEY_PREFIX + "schedule_kind")
    cron_raw = values.get(KEY_PREFIX + "cron")
    mode_raw = values.get(KEY_PREFIX + "encryption_mode")
    try:
        schedule = Schedule(
            kind=ScheduleKind(kind_raw) if isinstance(kind_raw, str) else base.schedule.kind,
            interval_hours=_int(values, "interval_hours", base.schedule.interval_hours),
            cron=cron_raw if isinstance(cron_raw, str) and cron_raw else base.schedule.cron,
        )
    except (ValueError, BackupError):
        schedule = base.schedule
    notify = values.get(KEY_PREFIX + "notify_admins")
    enabled = values.get(KEY_PREFIX + "enabled")
    return BackupSettings(
        enabled=enabled if isinstance(enabled, bool) else base.enabled,
        schedule=schedule,
        keep_last=max(0, _int(values, "keep_last", base.keep_last)),
        keep_days=max(0, _int(values, "keep_days", base.keep_days)),
        encryption_mode=EncryptionMode(mode_raw)
        if isinstance(mode_raw, str) and mode_raw in EncryptionMode
        else base.encryption_mode,
        notify_admins=notify if isinstance(notify, bool) else base.notify_admins,
    )


def settings_to(settings: BackupSettings) -> dict[str, object]:
    return {
        KEY_PREFIX + "enabled": settings.enabled,
        KEY_PREFIX + "schedule_kind": settings.schedule.kind.value,
        KEY_PREFIX + "interval_hours": settings.schedule.interval_hours,
        KEY_PREFIX + "cron": settings.schedule.cron,
        KEY_PREFIX + "keep_last": settings.keep_last,
        KEY_PREFIX + "keep_days": settings.keep_days,
        KEY_PREFIX + "encryption_mode": settings.encryption_mode.value,
        KEY_PREFIX + "notify_admins": settings.notify_admins,
    }


def validate_settings(settings: BackupSettings) -> None:
    if not 0 <= settings.keep_last <= MAX_KEEP:
        raise BackupError(BackupErrorCode.invalid_input, "keep_last out of range", field="keep_last")
    if not 0 <= settings.keep_days <= 3650:  # noqa: PLR2004
        raise BackupError(BackupErrorCode.invalid_input, "keep_days out of range", field="keep_days")


def last_scheduled_from(values: Mapping[str, object]) -> datetime | None:
    raw = values.get(KEY_LAST_SCHEDULED)
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None
