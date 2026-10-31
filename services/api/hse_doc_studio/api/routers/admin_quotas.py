"""`/api/admin/quota-policy`, `/quota-overrides`, `/usage*`: квоты по видам ресурсов и использование."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request, Response, status

from hse_doc_studio.api.schemas.quotas import (
    AdminGatewayProvider,
    AdminQuotaDefault,
    AdminQuotaOverride,
    AdminQuotaPolicy,
    AdminTopConsumer,
    AdminUsageSummary,
    OwnerKindName,
    OwnerUsageResponse,
    ResetUsageRequest,
    SetAdminQuotaOverrideRequest,
    UpdateAdminQuotaPolicyRequest,
)
from hse_doc_studio.api.usage_view import owner_usage_view
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.jobs.quotas import QuotaOwnerKind, QuotaResource
from hse_doc_studio.core.quotas.kinds import KIND_SPECS, Period, QuotaKind, QuotaScope, period_start
from hse_doc_studio.core.quotas.policy import OnExceed, QuotaPolicy, QuotaPolicyError
from hse_doc_studio.use_cases.admin.ops_quota_policy import (
    AdminOwnerUsageUC,
    AdminUsageSummaryUC,
    DeleteQuotaOverrideUC,
    GetQuotaPolicyUC,
    ListQuotaOverridesUC,
    OverrideView,
    ResetUsageUC,
    SetQuotaOverrideUC,
    UpdateQuotaPolicyUC,
)
from hse_doc_studio.use_cases.ai_gateway.status import AiGatewayStatusUC

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _policy_view(policy: QuotaPolicy) -> AdminQuotaPolicy:
    return AdminQuotaPolicy(
        defaults=[
            AdminQuotaDefault(
                kind=kind.value,
                user=policy.default(kind, QuotaScope.user),
                org=policy.default(kind, QuotaScope.org),
            )
            for kind in KIND_SPECS
        ],
        warn_percent=policy.warn_percent,
        on_exceed=policy.on_exceed.value,
    )


@router.get("/quota-policy", response_model=AdminQuotaPolicy)
async def get_quota_policy(request: Request, response: Response) -> AdminQuotaPolicy:
    response.headers.update(_NO_STORE)
    return _policy_view(await (await _uc(request, GetQuotaPolicyUC)).execute(_actor()))


@router.put("/quota-policy", response_model=AdminQuotaPolicy)
async def put_quota_policy(
    body: UpdateAdminQuotaPolicyRequest, request: Request, response: Response
) -> AdminQuotaPolicy:
    response.headers.update(_NO_STORE)
    limits: dict[tuple[QuotaKind, QuotaScope], int | None] = {}
    for item in body.defaults:
        kind = QuotaKind(item.kind)
        limits[(kind, QuotaScope.user)] = item.user
        limits[(kind, QuotaScope.org)] = item.org
    try:
        policy = QuotaPolicy(limits=limits, warn_percent=body.warn_percent, on_exceed=OnExceed(body.on_exceed))
    except QuotaPolicyError as exc:
        raise IdentityError(IdentityErrorCode.input_invalid) from exc
    return _policy_view(await (await _uc(request, UpdateQuotaPolicyUC)).execute(_actor(), policy))


def _override_view(item: OverrideView) -> AdminQuotaOverride:
    return AdminQuotaOverride(
        owner_kind=item.owner_kind.value,
        owner_id=item.owner_id,
        owner_name=item.owner_name,
        resource=item.resource.value,
        hard_limit=item.hard_limit,
    )


@router.get("/quota-overrides", response_model=list[AdminQuotaOverride])
async def list_overrides(request: Request, response: Response) -> list[AdminQuotaOverride]:
    response.headers.update(_NO_STORE)
    return [_override_view(i) for i in await (await _uc(request, ListQuotaOverridesUC)).execute(_actor())]


@router.put("/quota-overrides", response_model=AdminQuotaOverride)
async def put_override(body: SetAdminQuotaOverrideRequest, request: Request, response: Response) -> AdminQuotaOverride:
    response.headers.update(_NO_STORE)
    try:
        saved = await (await _uc(request, SetQuotaOverrideUC)).execute(
            _actor(), QuotaOwnerKind(body.owner_kind), body.owner_id, QuotaResource(body.resource), body.hard_limit
        )
    except QuotaPolicyError as exc:
        raise IdentityError(IdentityErrorCode.input_invalid) from exc
    return _override_view(saved)


@router.delete("/quota-overrides", status_code=status.HTTP_204_NO_CONTENT)
async def delete_override(
    request: Request,
    owner_kind: OwnerKindName = Query(),
    owner_id: str = Query(min_length=1, max_length=64),
    resource: str = Query(),
) -> Response:
    try:
        parsed = QuotaResource(resource)
    except ValueError as exc:
        raise IdentityError(IdentityErrorCode.input_invalid) from exc
    await (await _uc(request, DeleteQuotaOverrideUC)).execute(_actor(), QuotaOwnerKind(owner_kind), owner_id, parsed)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/usage", response_model=OwnerUsageResponse)
async def owner_usage(
    request: Request,
    response: Response,
    owner_kind: OwnerKindName = Query(),
    owner_id: str = Query(min_length=1, max_length=64),
) -> OwnerUsageResponse:
    response.headers.update(_NO_STORE)
    usage = await (await _uc(request, AdminOwnerUsageUC)).execute(_actor(), QuotaOwnerKind(owner_kind), owner_id)
    return owner_usage_view(usage)


@router.get("/usage/summary", response_model=AdminUsageSummary)
async def usage_summary(request: Request, response: Response) -> AdminUsageSummary:
    response.headers.update(_NO_STORE)
    summary = await (await _uc(request, AdminUsageSummaryUC)).execute(_actor())
    policy = await (await _uc(request, GetQuotaPolicyUC)).execute(_actor())
    month = period_start(Period.month, datetime.now(UTC))
    return AdminUsageSummary(
        totals={kind.value: used for kind, used in summary.totals.items()},
        top_builds=[
            AdminTopConsumer(user_id=i.user_id, name=i.name, used=i.used) for i in summary.top[QuotaKind.builds]
        ],
        top_ai_tokens=[
            AdminTopConsumer(user_id=i.user_id, name=i.name, used=i.used)
            for i in summary.top[QuotaKind.ai_tokens_month]
        ],
        period_start=month.isoformat() if month is not None else "",
        on_exceed=policy.on_exceed.value,
    )


@router.post("/usage/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_usage(body: ResetUsageRequest, request: Request) -> Response:
    await (await _uc(request, ResetUsageUC)).execute(
        _actor(), QuotaOwnerKind(body.owner_kind), body.owner_id, QuotaKind(body.kind)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/ai-gateway", response_model=list[AdminGatewayProvider])
async def ai_gateway_status(request: Request, response: Response) -> list[AdminGatewayProvider]:
    response.headers.update(_NO_STORE)
    return [
        AdminGatewayProvider(
            id=str(i.provider_id),
            name=i.name,
            type=i.type,
            breaker=i.breaker.value,
            failures=i.failures,
            calls_24h=i.calls,
            errors_24h=i.errors,
            denied_24h=i.denied,
            input_tokens_24h=i.input_tokens,
            output_tokens_24h=i.output_tokens,
        )
        for i in await (await _uc(request, AiGatewayStatusUC)).execute(_actor())
    ]
