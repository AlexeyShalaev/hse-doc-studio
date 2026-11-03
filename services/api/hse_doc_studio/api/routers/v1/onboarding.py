"""Онбординг: состояние знакомства со Студией у текущего человека (локально и на сервере одинаково)."""

from __future__ import annotations

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.onboarding import OnboardingStateResponse, UpdateOnboardingRequest
from hse_doc_studio.core.onboarding.entities import (
    OnboardingInvalidError,
    OnboardingPatch,
    OnboardingState,
    OnboardingStatus,
)
from hse_doc_studio.use_cases.onboarding.state import GetOnboardingUC, ResetOnboardingUC, UpdateOnboardingUC

router = APIRouter(route_class=SafeDishkaRoute)


def _view(state: OnboardingState) -> OnboardingStateResponse:
    return OnboardingStateResponse(
        status=state.status.value,
        scenario_version=state.scenario_version,
        step=state.step,
        answers=dict(state.answers),
        started_at=state.started_at,
        finished_at=state.finished_at,
        updated_at=state.updated_at,
    )


@router.get("/onboarding", response_model=OnboardingStateResponse)
async def get_onboarding(uc: FromDishka[GetOnboardingUC]) -> OnboardingStateResponse:
    return _view(await uc.execute())


@router.patch("/onboarding", response_model=OnboardingStateResponse)
async def update_onboarding(
    body: UpdateOnboardingRequest, uc: FromDishka[UpdateOnboardingUC]
) -> OnboardingStateResponse:
    patch = OnboardingPatch(
        status=None if body.status is None else OnboardingStatus(body.status),
        scenario_version=body.scenario_version,
        step=body.step or None,
        clear_step=body.step == "",
        answers=None if body.answers is None else {str(k): v for k, v in body.answers.items()},
    )
    try:
        state = await uc.execute(patch)
    except OnboardingInvalidError as exc:
        raise HTTPException(
            status_code=422, detail=[{"loc": ["body", exc.field], "code": "invalid", "msg": str(exc)}]
        ) from exc
    return _view(state)


@router.post("/onboarding/reset", response_model=OnboardingStateResponse)
async def reset_onboarding(uc: FromDishka[ResetOnboardingUC]) -> OnboardingStateResponse:
    return _view(await uc.execute())
