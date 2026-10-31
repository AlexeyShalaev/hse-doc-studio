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


class AdminGatewayProvider(StrictModel):
    id: str
    name: str
    type: str
    breaker: Literal["closed", "open", "half_open"]
    failures: int
    calls_24h: int
    errors_24h: int
    denied_24h: int
    input_tokens_24h: int
    output_tokens_24h: int


AutoscaleModeName = Literal["off", "webhook", "compose"]
ScaleActionName = Literal["hold", "up", "down"]
ScaleReasonName = Literal[
    "below_min",
    "above_max",
    "queue_depth",
    "queue_wait",
    "at_max",
    "cooldown_up",
    "idle",
    "idle_wait",
    "cooldown_down",
    "at_min",
    "busy",
    "balanced",
]


class AutoscalePolicyBody(StrictModel):
    mode: AutoscaleModeName
    min_runners: int = Field(ge=0, le=200)
    max_runners: int = Field(ge=1, le=200)
    target_queue_per_slot: float = Field(ge=0.1, le=100)
    scale_up_wait_s: int = Field(ge=0, le=86400)
    cooldown_up_s: int = Field(ge=0, le=86400)
    cooldown_down_s: int = Field(ge=0, le=86400)
    idle_before_down_s: int = Field(ge=0, le=86400)
    step_up: int = Field(ge=1, le=200)
    step_down: int = Field(ge=1, le=200)
    webhook_url: str | None = Field(default=None, max_length=2048, pattern=r"^https?://")


class AutoscaleMetricsBody(StrictModel):
    queued: int
    oldest_wait_s: float
    running: int
    runners_online: int
    slots_total: int
    slots_busy: int


class AutoscaleDecisionBody(StrictModel):
    current: int
    desired: int
    action: ScaleActionName
    reason: ScaleReasonName
    wait_s: int


class AutoscaleOutcomeBody(StrictModel):
    at: AwareDatetime
    desired: int
    ok: bool
    error: str | None


class AutoscaleStatusBody(StrictModel):
    policy: AutoscalePolicyBody
    metrics: AutoscaleMetricsBody
    decision: AutoscaleDecisionBody
    last_outcome: AutoscaleOutcomeBody | None
    last_up_at: AwareDatetime | None
    last_down_at: AwareDatetime | None
    orchestrator_current: int | None
    evaluated_at: AwareDatetime
    # Секрет подписи webhook задаётся окружением, в ответе только факт.
    webhook_secret_set: bool
