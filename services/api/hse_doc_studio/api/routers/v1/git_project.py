"""Git-синхронизация проекта: эндпоинты под /projects/{project_id}/git.

Контракт тел и ответов: api/schemas/git_sync.py, эталоны в contracts/git-sync.
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException

from hse_doc_studio.api.schemas.git_sync import CiFile, CiPreviewResponse, CiRequest, CiWriteRequest, CiWriteResponse
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.git_sync.ci import CiInput, CiWriteInput, PreviewCiUC, WriteCiUC

router = APIRouter(route_class=DishkaRoute)


@router.post("/projects/{project_id}/git/ci/preview", response_model=CiPreviewResponse)
async def preview_ci(project_id: UUID, body: CiRequest, uc: FromDishka[PreviewCiUC]) -> CiPreviewResponse:
    try:
        result = await uc.execute(
            CiInput(
                project_id=project_id,
                provider=body.provider,
                docs=body.docs,
                publish=body.publish,
                triggers=body.triggers,
                image=body.image,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CiPreviewResponse(
        files=[CiFile(path=f.path, content=f.content, exists=f.exists, same=f.same) for f in result.files],
        command=result.command,
        notes=result.notes,
    )


@router.post("/projects/{project_id}/git/ci/write", response_model=CiWriteResponse)
async def write_ci(project_id: UUID, body: CiWriteRequest, uc: FromDishka[WriteCiUC]) -> CiWriteResponse:
    try:
        result = await uc.execute(
            CiWriteInput(
                project_id=project_id,
                provider=body.provider,
                docs=body.docs,
                publish=body.publish,
                triggers=body.triggers,
                image=body.image,
                overwrite=body.overwrite,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CiWriteResponse(written=result.written)
