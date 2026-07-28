from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query

from hse_doc_studio.api.schemas.synctex import (
    SyncTexBoxResponse,
    SyncTexForwardResponse,
    SyncTexInverseResponse,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.synctex.query_synctex import (
    SyncTexForwardInput,
    SyncTexInverseInput,
    SyncTexUC,
)

router = APIRouter(route_class=DishkaRoute)


@router.get(
    "/projects/{project_id}/documents/{doc_id}/synctex/forward",
    response_model=SyncTexForwardResponse,
)
async def synctex_forward(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[SyncTexUC],
    file: str = Query(..., description="Source file (path or basename)"),
    line: int = Query(..., ge=1),
) -> SyncTexForwardResponse:
    """Source (file, line) -> PDF boxes (page + position in PDF points)."""
    try:
        out = uc.forward(SyncTexForwardInput(project_id=project_id, doc_id=doc_id, file=file, line=line))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SyncTexForwardResponse(
        boxes=[SyncTexBoxResponse(page=b.page, x=b.x, y=b.y, width=b.width, height=b.height) for b in out.boxes]
    )


@router.get(
    "/projects/{project_id}/documents/{doc_id}/synctex/inverse",
    response_model=SyncTexInverseResponse,
)
async def synctex_inverse(
    project_id: UUID,
    doc_id: str,
    uc: FromDishka[SyncTexUC],
    page: int = Query(..., ge=1),
    x: float = Query(..., description="X in PDF points from the page's left"),
    y: float = Query(..., description="Y in PDF points from the page's top"),
) -> SyncTexInverseResponse:
    """PDF (page, x, y) -> source (file, line, column)."""
    try:
        out = uc.inverse(SyncTexInverseInput(project_id=project_id, doc_id=doc_id, page=page, x=x, y=y))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if out is None:
        raise HTTPException(status_code=404, detail="No source mapping at this position")
    return SyncTexInverseResponse(file=out.file, line=out.line, column=out.column)
