"""PDF проекта, выгруженные локальной Студией: список, файл и удаление (только сервер).

Приём файла лежит рядом с git (`PUT /git/-/projects/{id}/documents/{doc}/pdf`): локальной Студии открыт git-токен.
"""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.artifact_mapping import map_artifact
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas.artifacts import ProjectArtifactListResponse
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.artifacts.entities import PDF_MEDIA_TYPE, ArtifactError, ArtifactErrorCode
from hse_doc_studio.use_cases.artifacts.pdf import (
    DeleteProjectArtifactUC,
    ListProjectArtifactsUC,
    OpenProjectArtifactUC,
)

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(require_server_mode)])

_NOT_FOUND = {ArtifactErrorCode.not_found, ArtifactErrorCode.unknown_document}


def _http(exc: ArtifactError) -> HTTPException:
    return HTTPException(status_code=404 if exc.code in _NOT_FOUND else 403, detail=exc.message)


@router.get("/projects/{project_id}/artifacts", response_model=ProjectArtifactListResponse)
async def list_project_artifacts(
    project_id: UUID, uc: FromDishka[ListProjectArtifactsUC], doc_id: str | None = Query(default=None, max_length=128)
) -> ProjectArtifactListResponse:
    items = await uc.execute(project_id, doc_id=doc_id)
    return ProjectArtifactListResponse(
        items=[map_artifact(item) for item in items],
        max_pdf_bytes=settings.artifacts.max_pdf_bytes,
        keep_per_document=settings.artifacts.keep_per_document,
    )


@router.get("/projects/{project_id}/artifacts/{artifact_id}/file")
async def get_project_artifact_file(
    project_id: UUID, artifact_id: UUID, uc: FromDishka[OpenProjectArtifactUC]
) -> Response:
    try:
        opened = await uc.execute(project_id, artifact_id)
    except ArtifactError as exc:
        raise _http(exc) from exc
    artifact = opened.artifact
    return StreamingResponse(
        opened.chunks,
        media_type=PDF_MEDIA_TYPE,
        headers={
            "Content-Length": str(artifact.size),
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(artifact.file_name)}",
            "Cache-Control": "private, max-age=0, must-revalidate",
            "ETag": f'"{artifact.sha256}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/projects/{project_id}/artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_artifact(project_id: UUID, artifact_id: UUID, uc: FromDishka[DeleteProjectArtifactUC]) -> None:
    try:
        await uc.execute(require_actor(), project_id, artifact_id)
    except ArtifactError as exc:
        raise _http(exc) from exc
