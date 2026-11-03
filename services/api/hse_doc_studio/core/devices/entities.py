"""Подключённые Студии: что локальная Студия сообщает серверу и что сервер из этого показывает.

Только метаданные состояния (docs/design/connected-devices.md, раздел 4): имя устройства, версия, коды состояний,
числа и имена моделей. Путей на диске, содержимого документов и ключей здесь нет и быть не может: поля строго
ограничены по виду и длине, а `sanitize_*` вычищает управляющие символы и всё, что похоже на путь.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

DEVICE_ID_RE = re.compile(r"[0-9a-f]{32}")
MAX_DEVICE_NAME = 64
MAX_VERSION = 32
MAX_PROJECTS = 100
MAX_ENDPOINTS = 8
MAX_MODELS = 50
MAX_MODEL_NAME = 128
MAX_ENDPOINT_NAME = 32
MAX_DOC_ID = 128
MAX_CODE = 64
# Всё, что похоже на путь файловой системы, в имя не попадает: `/Users/ivan/…`, `C:\…`, `~/…`.
_PATH_LIKE = re.compile(r"(^|\s)([A-Za-z]:[\\/]|~[\\/]|\\\\|/(?:Users|home|var|etc|opt|mnt|tmp|root)\b)")
_ENDPOINT_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}")
_CODE_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_DOC_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")


class DeviceActivity(StrEnum):
    idle = "idle"
    syncing = "syncing"
    building = "building"


class DeviceOs(StrEnum):
    macos = "macos"
    windows = "windows"
    linux = "linux"
    other = "other"


class SyncCode(StrEnum):
    """Состояние синхронизации проекта на устройстве (коды `SyncUiState` без лишнего)."""

    synced = "synced"
    syncing = "syncing"
    ahead = "ahead"
    behind = "behind"
    diverged = "diverged"
    conflicts = "conflicts"
    offline = "offline"
    auth_failed = "auth_failed"
    blocked = "blocked"
    error = "error"
    unfetched = "unfetched"


class Presence(StrEnum):
    online = "online"
    offline = "offline"


class AiState(StrEnum):
    """Доступна ли модель через эту Студию облаку и, если нет, почему (интерфейс по коду даёт совет)."""

    ready = "ready"
    not_opened = "not_opened"
    runner_unpaired = "runner_unpaired"
    runner_offline = "runner_offline"
    runner_paused = "runner_paused"
    runner_revoked = "runner_revoked"
    disabled = "disabled"
    endpoint_unreachable = "endpoint_unreachable"
    no_models = "no_models"
    no_provider = "no_provider"
    studio_offline = "studio_offline"
    unknown = "unknown"


@dataclass(frozen=True)
class PresenceConfig:
    """Интервалы присутствия; сервер сообщает их Студии в ответе на сигнал."""

    interval_s: int = 60
    online_window_s: int = 180
    # Запись в БД не чаще: пока состояние не изменилось, сервер держит свежее время в памяти.
    persist_interval_s: int = 120
    retention_days: int = 60

    def online(self, last_seen_at: datetime, now: datetime) -> bool:
        return now - last_seen_at <= timedelta(seconds=self.online_window_s)


@dataclass(frozen=True)
class RunnerReport:
    """Раннер Студии глазами Студии; состояние на сервере берётся из таблицы раннеров, а не отсюда."""

    runner_id: str | None = None
    state: str | None = None
    running_jobs: int = 0


@dataclass(frozen=True)
class EndpointReport:
    name: str
    flavor: str
    reachable: bool | None
    models: tuple[str, ...] = ()


@dataclass(frozen=True)
class PdfReport:
    doc_id: str
    at: datetime
    ok: bool
    code: str | None = None


@dataclass(frozen=True)
class ProjectReport:
    project_id: UUID
    sync: SyncCode
    ahead: int = 0
    behind: int = 0
    last_sync_at: datetime | None = None
    auto_sync: bool = False
    pdf: PdfReport | None = None


@dataclass(frozen=True)
class DeviceReport:
    """Сигнал присутствия: уже проверенный и очищенный, готовый к хранению."""

    device_id: str
    name: str
    version: str
    os: DeviceOs
    activity: DeviceActivity
    runner: RunnerReport | None = None
    endpoints: tuple[EndpointReport, ...] = ()
    projects: tuple[ProjectReport, ...] = ()


@dataclass(frozen=True)
class ConnectedDevice:
    """Устройство человека на сервере: последний сигнал и когда он пришёл."""

    user_id: str
    device_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    report: DeviceReport
    token_id: str | None = None
    project_ids: tuple[UUID, ...] = field(default=())


def clean_text(value: str, limit: int) -> str:
    """Строка без управляющих символов, с обрезкой по длине и схлопнутыми пробелами."""
    text = "".join(ch for ch in unicodedata.normalize("NFC", value) if unicodedata.category(ch)[0] != "C" or ch == " ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def sanitize_name(value: str) -> str:
    """Имя устройства: человеческое имя без путей. Пустое после очистки заменяется вызывающим."""
    name = clean_text(value, MAX_DEVICE_NAME)
    return "" if _PATH_LIKE.search(name) else name


def sanitize_endpoint_name(value: str) -> str | None:
    name = value.strip().lower()
    return name if _ENDPOINT_RE.fullmatch(name) else None


def sanitize_code(value: str | None) -> str | None:
    if value is None:
        return None
    return value if _CODE_RE.fullmatch(value) else None


def sanitize_doc_id(value: str) -> str | None:
    return value if _DOC_RE.fullmatch(value) else None


def sanitize_model(value: str) -> str | None:
    name = clean_text(value, MAX_MODEL_NAME)
    if not name or _PATH_LIKE.search(name):
        return None
    return name


def os_of(value: str | None) -> DeviceOs:
    try:
        return DeviceOs(value or "other")
    except ValueError:
        return DeviceOs.other
