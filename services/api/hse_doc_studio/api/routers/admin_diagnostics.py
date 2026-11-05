"""`/api/admin/diagnostics`: состояние проверок, ручной прогон, пороги."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.schemas.diagnostics import (
    DiagAcceptanceBody,
    DiagAcceptedBody,
    DiagAcceptRequest,
    DiagCheckBody,
    DiagOverviewBody,
    DiagRunRequest,
    DiagThresholdBody,
    DiagThresholdsRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.diagnostics.acceptance import Acceptance
from hse_doc_studio.core.diagnostics.thresholds import BOUNDS, DEFAULTS
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.diagnostics.admin import (
    AcceptDiagnosticsWarningUC,
    CheckView,
    DiagnosticsOverview,
    GetDiagnosticsUC,
    RevokeDiagnosticsAcceptanceUC,
    RunDiagnosticsUC,
    UpdateDiagnosticsThresholdsUC,
)

router = APIRouter(prefix="/diagnostics")

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


def _acceptance(acc: Acceptance) -> DiagAcceptanceBody:
    return DiagAcceptanceBody(reason=acc.reason, by_name=acc.by_name, at=acc.at, until=acc.until)


def _check(view: CheckView) -> DiagCheckBody:
    state = view.state
    result = state.result if state else None
    return DiagCheckBody(
        id=view.spec.id.value,
        group=view.spec.group.value,
        status=result.status.name if result else None,
        reason=result.reason if result else None,
        hint=result.hint if result else None,
        values=dict(result.values) if result else {},
        applicable=result.applicable if result else True,
        acceptable=view.acceptable,
        accepted=_acceptance(view.accepted) if view.accepted else None,
        checked_at=result.checked_at if result else None,
        status_since=state.status_since if state else None,
        duration_ms=result.duration_ms if result else None,
    )


def overview_body(view: DiagnosticsOverview) -> DiagOverviewBody:
    return DiagOverviewBody(
        overall=view.overall.name,
        enabled=view.enabled,
        interval_s=view.interval_s,
        last_tick_at=view.last_tick_at,
        checks=[_check(c) for c in view.checks],
        accepted=[
            DiagAcceptedBody(check=a.acceptance.check_id, acceptance=_acceptance(a.acceptance), active=a.active)
            for a in view.accepted
        ],
        thresholds=[
            DiagThresholdBody(
                name=name,
                value=int(getattr(view.thresholds, name)),
                default=int(getattr(DEFAULTS, name)),
                min=lo,
                max=hi,
            )
            for name, (lo, hi) in BOUNDS.items()
        ],
        notify=view.thresholds.notify,
    )


@router.get("", response_model=DiagOverviewBody)
async def get_diagnostics(request: Request, response: Response) -> DiagOverviewBody:
    response.headers.update(_NO_STORE)
    return overview_body(await (await request.state.dishka_container.get(GetDiagnosticsUC)).execute(_actor()))


@router.post("/run", response_model=DiagOverviewBody)
async def run_diagnostics(body: DiagRunRequest, request: Request, response: Response) -> DiagOverviewBody:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(RunDiagnosticsUC)
    return overview_body(await uc.execute(_actor(), body.check))


@router.put("/thresholds", response_model=DiagOverviewBody)
async def put_thresholds(body: DiagThresholdsRequest, request: Request, response: Response) -> DiagOverviewBody:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(UpdateDiagnosticsThresholdsUC)
    return overview_body(await uc.execute(_actor(), body.values, body.notify))


@router.put("/accepted/{check}", response_model=DiagOverviewBody)
async def accept_warning(check: str, body: DiagAcceptRequest, request: Request, response: Response) -> DiagOverviewBody:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(AcceptDiagnosticsWarningUC)
    return overview_body(await uc.execute(_actor(), check, body.reason, body.until))


@router.delete("/accepted/{check}", response_model=DiagOverviewBody)
async def revoke_acceptance(check: str, request: Request, response: Response) -> DiagOverviewBody:
    response.headers.update(_NO_STORE)
    uc = await request.state.dishka_container.get(RevokeDiagnosticsAcceptanceUC)
    return overview_body(await uc.execute(_actor(), check))
