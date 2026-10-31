"""Формы квот по видам ресурсов: использование, умолчания установки, переопределения (эталон `contracts/server`)."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.core.quotas.policy import MAX_LIMIT

QuotaKindName = Literal["storage", "builds", "ai_tokens_day", "ai_tokens_month", "members"]
QuotaScopeName = Literal["user", "org"]
QuotaStateName = Literal["unlimited", "ok", "warning", "exceeded"]
LimitSourceName = Literal["user", "org", "installation"]
OnExceedName = Literal["deprioritize", "reject", "warn"]
OwnerKindName = Literal["user", "org"]
ResourceName = Literal[
    "jobs.concurrent_user",
    "jobs.concurrent_org",
    "jobs.max_duration_s",
    "storage.bytes_user",
    "storage.bytes_org",
    "builds.month_user",
    "builds.month_org",
    "ai.tokens_day_user",
    "ai.tokens_day_org",
    "ai.tokens_month_user",
    "ai.tokens_month_org",
    "members.project_user",
    "members.project_org",
]


class UsageLine(StrictModel):
    """Один вид ресурса: сколько израсходовано, предел и откуда он взят. `limit` пуст у вида без предела."""

    kind: QuotaKindName
    scope: QuotaScopeName
    unit: str
    used: int
    limit: int | None
    percent: int | None
    state: QuotaStateName
    source: LimitSourceName | None
    resets_at: AwareDatetime | None


class OwnerUsageResponse(StrictModel):
    owner_id: str
    owner_name: str
    lines: list[UsageLine]


class MyUsageResponse(StrictModel):
    user: OwnerUsageResponse
    orgs: list[OwnerUsageResponse]
    warn_percent: int


class AdminQuotaDefault(StrictModel):
    kind: QuotaKindName
    user: int | None = Field(ge=1, le=MAX_LIMIT)
    org: int | None = Field(ge=1, le=MAX_LIMIT)


class AdminQuotaPolicy(StrictModel):
    defaults: list[AdminQuotaDefault]
    warn_percent: int = Field(ge=1, le=100)
    on_exceed: OnExceedName


class UpdateAdminQuotaPolicyRequest(AdminQuotaPolicy):
    """Полная замена: `null` снимает умолчание."""


class AdminQuotaOverride(StrictModel):
    owner_kind: OwnerKindName
    owner_id: str
    owner_name: str
    resource: ResourceName
    hard_limit: int


class SetAdminQuotaOverrideRequest(StrictModel):
    owner_kind: OwnerKindName
    owner_id: str = Field(min_length=1, max_length=64)
    resource: ResourceName
    hard_limit: int = Field(ge=1, le=MAX_LIMIT)


class AdminTopConsumer(StrictModel):
    user_id: str
    name: str
    used: int


class AdminUsageSummary(StrictModel):
    totals: dict[QuotaKindName, int]
    top_builds: list[AdminTopConsumer]
    top_ai_tokens: list[AdminTopConsumer]
    period_start: str
    on_exceed: OnExceedName


class ResetUsageRequest(StrictModel):
    owner_kind: OwnerKindName
    owner_id: str = Field(min_length=1, max_length=64)
    kind: QuotaKindName
