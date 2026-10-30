"""Админка эксплуатации (`/api/admin`): очередь, квоты, сервисы, хранилище, политика подписи, общие ИИ-провайдеры.

Формы совпадают с эталонами `contracts/server/fixtures/Admin*`. Ключи провайдеров принимаются на запись
и в ответах не возвращаются никогда.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.jobs.quotas import MAX_CONCURRENT, MAX_DURATION_S, MIN_DURATION_S

JobStateName = Literal["queued", "running", "succeeded", "failed", "cancelled", "timed_out"]
JobKindName = Literal["compile", "office.convert", "signature.verify_detached", "pack.submission"]
ServiceStateName = Literal["ok", "down", "degraded", "not_configured"]
AiProviderTypeName = Literal["claude", "openai", "openai_compat", "ollama"]


class AdminJob(StrictModel):
    id: str
    kind: JobKindName
    state: JobStateName
    project_id: str
    user_id: str
    org_id: str | None
    tags: list[str]
    priority_class: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    attempt: int
    max_attempts: int
    runner_id: str | None
    cancel_requested: bool
    error_code: str | None
    # Подписи для экрана; `null`, если записи уже нет (человек удалён, раннер ещё не назначен).
    user_name: str | None
    user_email: str | None
    org_name: str | None
    project_name: str | None
    runner_name: str | None


class AdminJobPage(StrictModel):
    """Журнал очереди: новые первыми, `next_cursor` непрозрачный, `null` на последней странице."""

    items: list[AdminJob]
    next_cursor: str | None
    # Оценка числа задач по статистике таблицы, только без фильтров; иначе `null`.
    total_estimate: int | None


class AdminQueueSummary(StrictModel):
    by_state: dict[str, int]
    queued_by_class: dict[str, int]
    oldest_queued_at: datetime | None
    wait_p50_s: float | None
    wait_p95_s: float | None


class AdminQuotas(StrictModel):
    user_concurrent: int | None
    org_concurrent: int | None
    max_duration_s: int | None
    # Поведение при исчерпании на этапе 2 не настраивается: задача ждёт в очереди.
    on_exhausted: Literal["wait"]


class UpdateAdminQuotasRequest(StrictModel):
    """Полная замена: `null` снимает лимит."""

    user_concurrent: int | None = Field(ge=1, le=MAX_CONCURRENT)
    org_concurrent: int | None = Field(ge=1, le=MAX_CONCURRENT)
    max_duration_s: int | None = Field(ge=MIN_DURATION_S, le=MAX_DURATION_S)


class AdminServiceHealth(StrictModel):
    id: str
    state: ServiceStateName
    reason: str | None
    total: int | None
    online: int | None


class AdminStorageOwner(StrictModel):
    owner_id: str
    owner_name: str
    projects: int


class AdminStorageOwnerRow(StrictModel):
    """Строка списка владельцев: человек или организация, число живых проектов и место по последнему замеру."""

    kind: Literal["user", "org"]
    id: str
    name: str
    email: str | None
    projects: int
    bytes: int


class AdminStorageUsage(StrictModel):
    blob_count: int
    blob_bytes: int
    projects: int
    deleted_projects: int
    top_owners: list[AdminStorageOwner]
    volume_total_bytes: int | None
    volume_free_bytes: int | None
    computed_at: datetime | None


class AdminSigningPolicy(StrictModel):
    server_keys: Literal["allowed", "forbidden"]
    # Сколько закрытых ключей уже лежит на сервере: при запрете они заблокированы, но не удалены.
    stored_keys: int


class UpdateAdminSigningPolicyRequest(StrictModel):
    server_keys: Literal["allowed", "forbidden"]


class AdminAiProvider(StrictModel):
    id: str
    name: str
    type: AiProviderTypeName
    base_url: str
    models: list[str]
    key_set: bool
    ssl_verify: bool
    connect_timeout_s: float
    request_timeout_s: float
    created_at: datetime


class CreateAdminAiProviderRequest(StrictModel):
    name: str = Field(min_length=1, max_length=128)
    type: AiProviderTypeName
    api_key: str = Field(max_length=4096)
    base_url: str = Field(max_length=2048)
    models: list[str] = Field(max_length=200)
    ssl_verify: bool
    connect_timeout_s: float = Field(gt=0, le=300)
    request_timeout_s: float = Field(gt=0, le=600)


class UpdateAdminAiProviderRequest(StrictModel):
    """`null` значит «не менять»; пустой `api_key` оставляет прежний ключ, стирает его только `clear_key`."""

    name: str | None = Field(max_length=128)
    type: AiProviderTypeName | None
    api_key: str | None = Field(max_length=4096)
    clear_key: bool
    base_url: str | None = Field(max_length=2048)
    models: list[str] | None = Field(max_length=200)
    ssl_verify: bool | None
    connect_timeout_s: float | None = Field(gt=0, le=300)
    request_timeout_s: float | None = Field(gt=0, le=600)


class AdminAiProviderCheck(StrictModel):
    ok: bool
    models: list[str]
    error: str | None
