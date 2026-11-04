"""Что видит человек: устройство целиком (своё) и «автор работает локально» (чужое)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.devices.entities import (
    AiState,
    DeviceActivity,
    DeviceOs,
    PdfReport,
    Presence,
    SyncCode,
)


@dataclass(frozen=True)
class RunnerView:
    """Личный раннер этой Студии по таблице раннеров сервера (а не по заявлению Студии)."""

    id: str
    name: str
    # online, stale, offline, paused, revoked, disabled (`RunnerStatus`).
    state: str
    tags: tuple[str, ...]
    concurrency: int
    running_jobs: int
    busy: bool


@dataclass(frozen=True)
class EndpointView:
    name: str
    flavor: str
    reachable: bool | None
    models: tuple[str, ...]
    provider_id: UUID | None = None
    provider_name: str | None = None
    state: AiState = AiState.unknown


@dataclass(frozen=True)
class AiView:
    state: AiState
    endpoints: tuple[EndpointView, ...] = ()


@dataclass(frozen=True)
class ProjectSyncView:
    sync: SyncCode
    ahead: int
    behind: int
    last_sync_at: datetime | None
    auto_sync: bool
    pdf: PdfReport | None


@dataclass(frozen=True)
class DeviceView:
    id: str
    name: str
    version: str
    os: DeviceOs
    presence: Presence
    last_seen_at: datetime
    activity: DeviceActivity
    projects_count: int
    runner: RunnerView | None = None
    ai: AiView = field(default_factory=lambda: AiView(AiState.unknown))
    project: ProjectSyncView | None = None
    # Устройство работает с проектом, который сейчас просматривают (для списка аккаунта пусто).
    project_id: UUID | None = None


@dataclass(frozen=True)
class WorkingLocally:
    """Чужая Студия в проекте: только кто и что он в сети сейчас. Ни имени машины, ни версии, ни раннера."""

    user_id: str
    name: str


@dataclass(frozen=True)
class ProjectStudios:
    online_window_s: int
    mine: tuple[DeviceView, ...]
    others: tuple[WorkingLocally, ...]


@dataclass(frozen=True)
class AccountDevices:
    online_window_s: int
    items: tuple[DeviceView, ...]
