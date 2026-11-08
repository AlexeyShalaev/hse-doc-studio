"""План подписей проекта, профиля сдачи или документа (docs/design/signature-plan.md)."""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.signature_plan import SignaturePlanResponse, map_plan
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.signatures.get_signature_plan import GetSignaturePlanInput, GetSignaturePlanUC

router = APIRouter(route_class=SafeDishkaRoute)


@router.get("/projects/{project_id}/signature-plan", response_model=SignaturePlanResponse)
async def get_signature_plan(
    project_id: UUID,
    uc: FromDishka[GetSignaturePlanUC],
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
    return map_plan(plan)
