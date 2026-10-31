"""`/api/admin/autoscale`: политика, метрики очереди и решение автомасштабирования раннеров."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.schemas.quotas import (
    AutoscaleDecisionBody,
    AutoscaleMetricsBody,
    AutoscaleOutcomeBody,
    AutoscalePolicyBody,
    AutoscaleStatusBody,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.jobs.autoscale import AutoscaleMode, AutoscalePolicy, AutoscaleValueError
from hse_doc_studio.use_cases.jobs.autoscale import AutoscaleStatus, GetAutoscaleUC, UpdateAutoscaleUC

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


def _policy_body(policy: AutoscalePolicy) -> AutoscalePolicyBody:
    return AutoscalePolicyBody(
        mode=policy.mode.value,
        min_runners=policy.min_runners,
        max_runners=policy.max_runners,
        target_queue_per_slot=policy.target_queue_per_slot,
        scale_up_wait_s=policy.scale_up_wait_s,
        cooldown_up_s=policy.cooldown_up_s,
        cooldown_down_s=policy.cooldown_down_s,
        idle_before_down_s=policy.idle_before_down_s,
        step_up=policy.step_up,
        step_down=policy.step_down,
        webhook_url=policy.webhook_url,
    )


def _status_body(status: AutoscaleStatus) -> AutoscaleStatusBody:
    m, d, o = status.metrics, status.decision, status.last_outcome
    return AutoscaleStatusBody(
        policy=_policy_body(status.policy),
        metrics=AutoscaleMetricsBody(
            queued=m.queued,
            oldest_wait_s=m.oldest_wait_s,
            running=m.running,
            runners_online=m.runners_online,
            slots_total=m.slots_total,
            slots_busy=m.slots_busy,
        ),
        decision=AutoscaleDecisionBody(
            current=d.current, desired=d.desired, action=d.action.value, reason=d.reason.value, wait_s=d.wait_s
        ),
        last_outcome=AutoscaleOutcomeBody(at=o.at, desired=o.desired, ok=o.ok, error=o.error) if o else None,
        last_up_at=status.last_up_at,
        last_down_at=status.last_down_at,
        orchestrator_current=status.orchestrator_current,
        evaluated_at=status.evaluated_at,
        webhook_secret_set=settings.autoscale.webhook_secret is not None,
    )


@router.get("/autoscale", response_model=AutoscaleStatusBody)
async def get_autoscale(request: Request, response: Response) -> AutoscaleStatusBody:
    response.headers.update(_NO_STORE)
    return _status_body(await (await request.state.dishka_container.get(GetAutoscaleUC)).execute(_actor()))


@router.put("/autoscale", response_model=AutoscaleStatusBody)
async def put_autoscale(body: AutoscalePolicyBody, request: Request, response: Response) -> AutoscaleStatusBody:
    response.headers.update(_NO_STORE)
    try:
        policy = AutoscalePolicy(
            mode=AutoscaleMode(body.mode),
            min_runners=body.min_runners,
            max_runners=body.max_runners,
            target_queue_per_slot=body.target_queue_per_slot,
            scale_up_wait_s=body.scale_up_wait_s,
            cooldown_up_s=body.cooldown_up_s,
            cooldown_down_s=body.cooldown_down_s,
            idle_before_down_s=body.idle_before_down_s,
            step_up=body.step_up,
            step_down=body.step_down,
            webhook_url=body.webhook_url or None,
        )
    except AutoscaleValueError as exc:
        raise IdentityError(IdentityErrorCode.input_invalid) from exc
    return _status_body(await (await request.state.dishka_container.get(UpdateAutoscaleUC)).execute(_actor(), policy))
