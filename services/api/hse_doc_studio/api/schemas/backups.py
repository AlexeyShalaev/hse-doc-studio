"""Формы `/api/admin/backups`: назначения, настройки, запуски. Секреты в ответы не попадают."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from hse_doc_studio.api.schemas.common import StrictModel

DestinationKindName = Literal["s3", "local"]
RunStatusName = Literal["running", "ok", "failed", "interrupted"]
RunTriggerName = Literal["manual", "schedule"]
ScheduleKindName = Literal["interval", "cron"]
EncryptionModeName = Literal["installation", "passphrase"]


class DestinationBody(StrictModel):
    """Ввод назначения. Пустые ключи при правке значат «оставить как есть»."""

    name: str = Field(max_length=128)
    kind: DestinationKindName
    endpoint: str | None = Field(default=None, max_length=512)
    region: str = Field(default="us-east-1", max_length=64)
    bucket: str | None = Field(default=None, max_length=256)
    prefix: str = Field(default="", max_length=512)
    path_style: bool = True
    local_path: str | None = Field(default=None, max_length=512)
    access_key: str | None = Field(default=None, max_length=256, repr=False)
    secret_key: str | None = Field(default=None, max_length=512, repr=False)
    make_default: bool = False


class CheckDestinationBody(StrictModel):
    """Проверка формы до сохранения; `destination_id` подставляет сохранённые ключи вместо пустых."""

    destination_id: str | None = None
    destination: DestinationBody


class DestinationInfo(StrictModel):
    id: str
    name: str
    kind: DestinationKindName
    is_default: bool
    endpoint: str | None
    region: str
    bucket: str | None
    prefix: str
    path_style: bool
    local_path: str | None
    access_key_hint: str | None
    secret_key_set: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime
    last_check_at: AwareDatetime | None
    last_check_ok: bool | None
    last_check_error: str | None


class CheckResultInfo(StrictModel):
    ok: bool
    error: str | None
    warnings: list[str]
    checked_at: AwareDatetime


class RunInfo(StrictModel):
    id: str
    destination_id: str | None
    destination_name: str
    trigger: RunTriggerName
    status: RunStatusName
    stage: str | None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None
    duration_s: float | None
    size_bytes: int | None
    backup_id: str | None
    error: str | None
    removed_at: AwareDatetime | None


class RunPage(StrictModel):
    items: list[RunInfo]
    total: int
    limit: int
    offset: int


class StartRunBody(StrictModel):
    destination_id: str | None = None


class SettingsBody(StrictModel):
    enabled: bool
    schedule_kind: ScheduleKindName
    interval_hours: int = Field(ge=1, le=24 * 90)
    cron: str = Field(max_length=128)
    keep_last: int = Field(ge=0, le=10_000)
    keep_days: int = Field(ge=0, le=3650)
    encryption_mode: EncryptionModeName
    notify_admins: bool
    # None оставляет сохранённую фразу; значение заменяет её. Обратно фраза не отдаётся.
    passphrase: str | None = Field(default=None, max_length=256, repr=False)


class SettingsInfo(StrictModel):
    enabled: bool
    schedule_kind: ScheduleKindName
    interval_hours: int
    cron: str
    keep_last: int
    keep_days: int
    encryption_mode: EncryptionModeName
    notify_admins: bool
    passphrase_set: bool


class StatusInfo(StrictModel):
    settings: SettingsInfo
    next_run_at: AwareDatetime | None
    last_scheduled_at: AwareDatetime | None
    running: RunInfo | None
    last_run: RunInfo | None
    local_root: str
    destinations_total: int


class StoredBackupPart(StrictModel):
    name: str
    size: int
    plain_size: int


class StoredBackupInfo(StrictModel):
    backup_id: str
    created_at: AwareDatetime
    app_version: str
    schema_revision: str | None
    installation_id: str | None
    encryption_mode: EncryptionModeName
    size: int
    parts: list[StoredBackupPart]
    manifest_sha256: str
    restore_command: str
