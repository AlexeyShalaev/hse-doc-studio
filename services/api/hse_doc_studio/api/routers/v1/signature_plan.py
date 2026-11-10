"""План подписей проекта, профиля сдачи или документа (docs/design/signature-plan.md)."""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.signature_plan import (
    SignaturePlanResponse,
    SignPreviewResponse,
    SignSubmissionRequest,
    SignSubmissionResponse,
    map_plan,
    map_preview,
    map_results,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.signing_route.ports import ISigningRouteGate
from hse_doc_studio.use_cases.signatures.get_signature_plan import GetSignaturePlanInput, GetSignaturePlanUC
from hse_doc_studio.use_cases.signatures.sign_submission import (
    SigningConflictError,
    SignSubmissionInput,
    SignSubmissionUC,
)

router = APIRouter(route_class=SafeDishkaRoute)


@router.get("/projects/{project_id}/signature-plan", response_model=SignaturePlanResponse)
async def get_signature_plan(
    project_id: UUID,
    uc: FromDishka[GetSignaturePlanUC],
    routes: FromDishka[ISigningRouteGate],
    profile_id: str | None = Query(default=None),
    author: str | None = Query(default=None),
    doc_id: str | None = Query(default=None),
) -> SignaturePlanResponse:
    try:
        plan = await uc.execute(
            GetSignaturePlanInput(project_id=project_id, profile_id=profile_id, author=author, doc_id=doc_id)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return map_plan(plan, await routes.plan_routes(project_id, profile_id=profile_id, doc_id=doc_id))


def _sign_input(project_id: UUID, body: SignSubmissionRequest) -> SignSubmissionInput:
    return SignSubmissionInput(
        project_id=project_id,
        profile_id=body.profile_id,
        author=body.author,
        identity_id=body.identity_id,
        passphrase=body.passphrase,
        confirm_reset=body.confirm_reset,
        expected=body.expected,
    )


@router.post("/projects/{project_id}/signature-plan/sign-preview", response_model=SignPreviewResponse)
async def preview_sign_submission(
    project_id: UUID, body: SignSubmissionRequest, uc: FromDishka[SignSubmissionUC]
) -> SignPreviewResponse:
    """Что сделает «Подписать комплект»: фиксации, сбросы чужих подписей, свои слоты, ключ и пароль."""
    try:
        return map_preview(await uc.preview(_sign_input(project_id, body)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/projects/{project_id}/signature-plan/sign", response_model=SignSubmissionResponse)
async def sign_submission(
    project_id: UUID,
    body: SignSubmissionRequest,
    uc: FromDishka[SignSubmissionUC],
    plan_uc: FromDishka[GetSignaturePlanUC],
    routes: FromDishka[ISigningRouteGate],
) -> SignSubmissionResponse:
    """«Подписать комплект»: фиксирует нужные PDF и подписывает все слоты актора его ключом, пароль один раз."""
    try:
        out = await uc.execute(_sign_input(project_id, body))
        plan = await plan_uc.execute(
            GetSignaturePlanInput(project_id=project_id, profile_id=body.profile_id, author=body.author)
        )
    except SigningConflictError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return map_results(out, plan, await routes.plan_routes(project_id, profile_id=body.profile_id))
