"""Операционные экраны админки: очередь задач, квоты, здоровье сервисов, место (`/api/admin`).

Форма зафиксирована эталонами `contracts/server/fixtures` раньше самих ручек: экраны SPA работают
на демо-мире, а бэкенд очереди, квот и сервисов реализует эти же тела. Раннеры и токены регистрации
описаны в `runner_admin.py` (ручки уже смонтированы).

Тексты ошибок задач обрезаны и не содержат путей пользователей: админ видит только метаданные.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.session import SettingState

JobStateName = Literal["queued", "running", "succeeded", "failed", "cancelled", "timed_out"]
JobPriorityName = Literal["interactive", "checks", "batch"]
ServiceStatusName = Literal["ok", "degraded", "down", "unconfigured"]
ServiceKindName = Literal["database", "storage", "languagetool", "onlyoffice", "runners", "smtp"]


class AdminJob(StrictModel):
    id: str
    kind: str
    status: JobStateName
    priority: JobPriorityName
    project_id: str | None
    project_name: str | None
    user_id: str
    user_name: str
    tags: list[str]
    runner_id: str | None
    runner_name: str | None
    attempt: int
    max_attempts: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    # Сколько задача ждала (или ждёт) раннера, секунды.
    wait_s: int
    # Короткая причина отказа без путей; null у не упавших.
    error: str | None


class AdminJobPage(StrictModel):
    items: list[AdminJob]
    total: int


class AdminQueueTag(StrictModel):
    tag: str
    queued: int
    running: int
    avg_wait_s: int | None


class AdminQueueSummary(StrictModel):
    queued: int
    running: int
    oldest_queued_age_s: int | None
    wait_p50_s: int | None
    wait_p95_s: int | None
    tags: list[AdminQueueTag]


class AdminQuotaOverride(StrictModel):
    org_slug: str
    org_name: str
    # null значит «как по умолчанию установки».
    jobs_concurrent: int | None
    jobs_max_duration_s: int | None


class AdminQuotas(StrictModel):
    jobs_concurrent: int
    jobs_max_duration_s: int
    fields: dict[str, SettingState]
    overrides: list[AdminQuotaOverride]


class UpdateAdminQuotasRequest(StrictModel):
    jobs_concurrent: int | None = Field(default=None, ge=1, le=64)
    jobs_max_duration_s: int | None = Field(default=None, ge=30, le=86400)


class SetAdminQuotaOverrideRequest(StrictModel):
    jobs_concurrent: int | None = Field(default=None, ge=1, le=64)
    jobs_max_duration_s: int | None = Field(default=None, ge=30, le=86400)


class AdminServiceReplica(StrictModel):
    name: str
    status: ServiceStatusName
    latency_ms: int | None
    slots_used: int | None
    slots_total: int | None


class AdminService(StrictModel):
    id: str
    kind: ServiceKindName
    status: ServiceStatusName
    latency_ms: int | None
    # Причина, если сервис не в порядке; без адресов и секретов.
    detail: str | None
    checked_at: datetime
    replicas: list[AdminServiceReplica]


class AdminStorageOwner(StrictModel):
    kind: Literal["user", "org"]
    id: str
    name: str
    bytes: int
    projects: int


class AdminStorage(StrictModel):
    total_bytes: int
    free_bytes: int | None
    volume_bytes: int
    object_bytes: int
    computed_at: datetime
    owners: list[AdminStorageOwner]
