"""Git-синхронизация проекта: эндпоинты под /projects/{project_id}/git.

Контракт тел и ответов: api/schemas/git_sync.py, эталоны в contracts/git-sync.
"""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, HTTPException, Query, Response, status

from hse_doc_studio.api.conflict_mapping import (
    map_diff,
    map_file_detail,
    map_session,
    resolutions_from_body,
)
from hse_doc_studio.api.git_mapping import map_status
from hse_doc_studio.api.schemas.git_sync import (
    CiFile,
    CiPreviewResponse,
    CiRequest,
    CiWriteRequest,
    CiWriteResponse,
    ConflictDiffResponse,
    ConflictFileDetail,
    ConflictSessionResponse,
    ConnectRemoteRequest,
    GitStatusResponse,
    OperationStartedResponse,
    ResolveConflictsRequest,
    SaveConflictDraftRequest,
    UpdateGitSettingsRequest,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.git_sync.abort_conflicts import AbortConflictsInput, AbortConflictsUC
from hse_doc_studio.use_cases.git_sync.ci import CiInput, CiWriteInput, PreviewCiUC, WriteCiUC
from hse_doc_studio.use_cases.git_sync.connect_remote import (
    ConnectRemoteInput,
    ConnectRemoteUC,
    DisconnectRemoteInput,
    DisconnectRemoteUC,
)
from hse_doc_studio.use_cases.git_sync.get_conflict_diff import (
    ConflictDiffView,
    GetConflictDiffInput,
    GetConflictDiffUC,
)
from hse_doc_studio.use_cases.git_sync.get_conflict_file import (
    BlobSide,
    GetConflictBlobInput,
    GetConflictBlobUC,
    GetConflictFileInput,
    GetConflictFileUC,
)
from hse_doc_studio.use_cases.git_sync.get_conflicts import GetConflictsInput, GetConflictsUC
from hse_doc_studio.use_cases.git_sync.resolve_conflicts import ResolveConflictsInput, ResolveConflictsUC
from hse_doc_studio.use_cases.git_sync.save_draft import SaveDraftInput, SaveDraftUC
from hse_doc_studio.use_cases.git_sync.start_sync import StartSyncInput, StartSyncUC
from hse_doc_studio.use_cases.git_sync.status import GetGitStatusInput, GetGitStatusUC
from hse_doc_studio.use_cases.git_sync.update_git_settings import UpdateGitSettingsInput, UpdateGitSettingsUC

router = APIRouter(route_class=DishkaRoute)


@router.get("/projects/{project_id}/git", response_model=GitStatusResponse)
async def get_git_status(project_id: UUID, uc: FromDishka[GetGitStatusUC]) -> GitStatusResponse:
    try:
        return map_status(await uc.execute(GetGitStatusInput(project_id=project_id)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/projects/{project_id}/git/remote", response_model=GitStatusResponse)
async def connect_git_remote(
    project_id: UUID, body: ConnectRemoteRequest, uc: FromDishka[ConnectRemoteUC]
) -> GitStatusResponse:
    try:
        view = await uc.execute(
            ConnectRemoteInput(
                project_id=project_id,
                url=body.url,
                credential_id=body.credential_id,
                branch=body.branch,
                remote_branch=body.remote_branch,
                adopt=body.adopt,
                insecure_http=bool(body.insecure_http),
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return map_status(view)


@router.delete("/projects/{project_id}/git/remote", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_git_remote(
    project_id: UUID, uc: FromDishka[DisconnectRemoteUC], forget_credential: bool = False
) -> None:
    try:
        await uc.execute(DisconnectRemoteInput(project_id=project_id, forget_credential=forget_credential))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/projects/{project_id}/git/settings", response_model=GitStatusResponse)
async def update_git_settings(
    project_id: UUID, body: UpdateGitSettingsRequest, uc: FromDishka[UpdateGitSettingsUC]
) -> GitStatusResponse:
    try:
        view = await uc.execute(
            UpdateGitSettingsInput(
                project_id=project_id,
                auto_fetch=body.auto_fetch,
                interval_given="interval_s" in body.model_fields_set,
                interval_s=body.interval_s,
                shared_folder_ack=body.shared_folder_ack,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return map_status(view)


@router.post("/projects/{project_id}/git/sync", response_model=OperationStartedResponse, status_code=202)
async def start_git_sync(project_id: UUID, uc: FromDishka[StartSyncUC]) -> OperationStartedResponse:
    try:
        started = await uc.execute(StartSyncInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OperationStartedResponse(operation_id=started.operation_id)


@router.get("/projects/{project_id}/git/conflicts", response_model=ConflictSessionResponse)
async def get_git_conflicts(project_id: UUID, uc: FromDishka[GetConflictsUC]) -> ConflictSessionResponse:
    try:
        return map_session(await uc.execute(GetConflictsInput(project_id=project_id)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/git/conflicts/file", response_model=ConflictFileDetail)
async def get_git_conflict_file(
    project_id: UUID, uc: FromDishka[GetConflictFileUC], path: str = Query(min_length=1)
) -> ConflictFileDetail:
    try:
        return map_file_detail(await uc.execute(GetConflictFileInput(project_id=project_id, path=path)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/git/conflicts/diff", response_model=ConflictDiffResponse)
async def get_git_conflict_diff(
    project_id: UUID,
    uc: FromDishka[GetConflictDiffUC],
    view: ConflictDiffView,
    path: str = Query(min_length=1),
) -> ConflictDiffResponse:
    try:
        return map_diff(await uc.execute(GetConflictDiffInput(project_id=project_id, path=path, view=view)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/git/conflicts/blob")
async def get_git_conflict_blob(
    project_id: UUID,
    uc: FromDishka[GetConflictBlobUC],
    side: BlobSide,
    path: str = Query(min_length=1),
) -> Response:
    try:
        blob = await uc.execute(GetConflictBlobInput(project_id=project_id, path=path, side=side))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Содержимое чужое: показывать его на странице Студии нельзя, поэтому только безопасные типы и без угадывания.
    return Response(
        content=blob.content,
        media_type=blob.media_type,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(blob.filename)}",
        },
    )


@router.put("/projects/{project_id}/git/conflicts/draft", status_code=status.HTTP_204_NO_CONTENT)
async def save_git_conflict_draft(
    project_id: UUID, body: SaveConflictDraftRequest, uc: FromDishka[SaveDraftUC]
) -> None:
    try:
        await uc.execute(SaveDraftInput(project_id=project_id, resolutions=resolutions_from_body(body.resolutions)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/git/conflicts/resolve", response_model=OperationStartedResponse, status_code=202)
async def resolve_git_conflicts(
    project_id: UUID, body: ResolveConflictsRequest, uc: FromDishka[ResolveConflictsUC]
) -> OperationStartedResponse:
    try:
        started = await uc.execute(
            ResolveConflictsInput(
                project_id=project_id,
                fingerprint=body.fingerprint,
                resolutions=None if body.resolutions is None else resolutions_from_body(body.resolutions),
                push=body.push,
            )
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OperationStartedResponse(operation_id=started.operation_id)


@router.delete("/projects/{project_id}/git/conflicts", response_model=GitStatusResponse)
async def abort_git_conflicts(project_id: UUID, uc: FromDishka[AbortConflictsUC]) -> GitStatusResponse:
    try:
        return map_status(await uc.execute(AbortConflictsInput(project_id=project_id)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
