"""Сущности бэкапов: назначения, запуски, настройки, манифест."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from hse_doc_studio.core.backup.schedule import Schedule

MANIFEST_NAME = "manifest.json"
MANIFEST_FORMAT = 1
PART_DB = "db.pgdump.enc"
PART_FILES = "files.tar.enc"
PART_OBJECTS = "objects.tar.enc"
PART_SETTINGS = "settings.json.enc"
PART_NAMES = (PART_DB, PART_FILES, PART_OBJECTS, PART_SETTINGS)
PROBE_PREFIX = "hse-write-test-"


class DestinationKind(StrEnum):
    s3 = "s3"
    local = "local"


class RunStatus(StrEnum):
    running = "running"
    ok = "ok"
    failed = "failed"
    interrupted = "interrupted"


class RunTrigger(StrEnum):
    manual = "manual"
    schedule = "schedule"


class EncryptionMode(StrEnum):
    installation = "installation"
    passphrase = "passphrase"  # noqa: S105 — имя режима, не пароль


@dataclass(frozen=True)
class DestinationSpec:
    """Не секретная часть назначения: что ввёл админ."""

    name: str
    kind: DestinationKind
    endpoint: str | None = None
    region: str = "us-east-1"
    bucket: str | None = None
    prefix: str = ""
    path_style: bool = True
    local_path: str | None = None


@dataclass(frozen=True)
class BackupDestination:
    id: str
    spec: DestinationSpec
    is_default: bool
    access_key_hint: str | None
    secret_key_set: bool
    created_at: datetime
    updated_at: datetime
    last_check_at: datetime | None = None
    last_check_ok: bool | None = None
    last_check_error: str | None = None


@dataclass(frozen=True)
class DestinationSecrets:
    """Расшифрованные ключи доступа: живут только на время обращения к хранилищу."""

    access_key: str | None = None
    secret_key: str | None = None


@dataclass(frozen=True)
class StoredDestination:
    """Назначение вместе со шифртекстами ключей (то, что хранит репозиторий)."""

    destination: BackupDestination
    access_key_enc: str | None
    secret_key_enc: str | None


@dataclass(frozen=True)
class BackupSettings:
    enabled: bool = False
    schedule: Schedule = field(default_factory=Schedule)
    keep_last: int = 7
    keep_days: int = 30
    encryption_mode: EncryptionMode = EncryptionMode.installation
    notify_admins: bool = True


@dataclass(frozen=True)
class ManifestPart:
    name: str
    size: int
    sha256: str
    plain_size: int
    plain_sha256: str


@dataclass(frozen=True)
class Manifest:
    format: int
    backup_id: str
    created_at: datetime
    app_version: str
    schema_revision: str | None
    installation_id: str | None
    encryption_mode: EncryptionMode
    salt_hex: str
    key_check: str
    key_fingerprint: str | None
    parts: tuple[ManifestPart, ...]
    notes: dict[str, int | str] = field(default_factory=dict)

    @property
    def total_size(self) -> int:
        return sum(part.size for part in self.parts)

    def part(self, name: str) -> ManifestPart | None:
        return next((part for part in self.parts if part.name == name), None)


@dataclass(frozen=True)
class BackupRun:
    id: str
    destination_id: str | None
    destination_name: str
    trigger: RunTrigger
    status: RunStatus
    stage: str | None
    started_at: datetime
    started_by: str | None = None
    finished_at: datetime | None = None
    size_bytes: int | None = None
    backup_id: str | None = None
    error: str | None = None
    manifest_sha256: str | None = None
    removed_at: datetime | None = None

    @property
    def duration_s(self) -> float | None:
        if self.finished_at is None:
            return None
        return max(0.0, (self.finished_at - self.started_at).total_seconds())


@dataclass(frozen=True)
class StoredBackup:
    """Бэкап, найденный в хранилище по манифесту."""

    backup_id: str
    manifest: Manifest
    manifest_sha256: str
