"""Git-синхронизация проекта: эндпоинты под /projects/{project_id}/git.

Контракт тел и ответов: api/schemas/git_sync.py, эталоны в contracts/git-sync.
"""

from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from hse_doc_studio.api.conflict_mapping import (
    map_diff,
    map_file_detail,
    map_session,
    resolutions_from_body,
)
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.git_mapping import map_status
from hse_doc_studio.api.schemas.git_sync import (
    BundleExportRequest,
    CiFile,
    CiPreviewResponse,
    CiRequest,
    CiWriteRequest,
    CiWriteResponse,
    ConflictDiffResponse,
    ConflictFileDetail,
    ConflictSessionResponse,
    ConnectRemoteRequest,
    GitContentsResponse,
    GitLargestFile,
    GitOverLimitFile,
    GitStatusResponse,
    OperationStartedResponse,
    PdfPublishRequest,
    PdfPublishResponse,
    ResolveConflictsRequest,
    SaveConflictDraftRequest,
    UpdateGitSettingsRequest,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.use_cases.git_sync.abort_conflicts import AbortConflictsInput, AbortConflictsUC
from hse_doc_studio.use_cases.git_sync.bundles import (
    BundleScratch,
    ExportBundleInput,
    ExportBundleUC,
    ImportBundleInput,
    ImportBundleUC,
)
from hse_doc_studio.use_cases.git_sync.ci import CiInput, CiWriteInput, PreviewCiUC, WriteCiUC
from hse_doc_studio.use_cases.git_sync.connect_remote import (
    ConnectRemoteInput,
    ConnectRemoteUC,
    DisconnectRemoteInput,
    DisconnectRemoteUC,
)
from hse_doc_studio.use_cases.git_sync.contents import GetGitContentsInput, GetGitContentsUC
from hse_doc_studio.use_cases.git_sync.fetch_remote import FetchGitRemoteInput, FetchGitRemoteUC
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
from hse_doc_studio.use_cases.git_sync.publish_pdf import PublishPdfUC
from hse_doc_studio.use_cases.git_sync.resolve_conflicts import ResolveConflictsInput, ResolveConflictsUC
from hse_doc_studio.use_cases.git_sync.save_draft import SaveDraftInput, SaveDraftUC
from hse_doc_studio.use_cases.git_sync.start_sync import StartSyncInput, StartSyncUC
from hse_doc_studio.use_cases.git_sync.status import GetGitStatusInput, GetGitStatusUC
from hse_doc_studio.use_cases.git_sync.update_git_settings import UpdateGitSettingsInput, UpdateGitSettingsUC

router = APIRouter(route_class=SafeDishkaRoute)


@router.get("/projects/{project_id}/git", response_model=GitStatusResponse)
async def get_git_status(project_id: UUID, uc: FromDishka[GetGitStatusUC]) -> GitStatusResponse:
    try:
        return map_status(await uc.execute(GetGitStatusInput(project_id=project_id)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/git/fetch", response_model=GitStatusResponse)
async def fetch_git_remote(project_id: UUID, uc: FromDishka[FetchGitRemoteUC]) -> GitStatusResponse:
    try:
        return map_status(await uc.execute(FetchGitRemoteInput(project_id=project_id)))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/projects/{project_id}/git/pdf", response_model=PdfPublishResponse)
async def publish_pdf_to_server(
    project_id: UUID, body: PdfPublishRequest, uc: FromDishka[PublishPdfUC]
) -> PdfPublishResponse:
    """Выгрузить собранный PDF документа на сервер Студии сейчас (автовыгрузка после сборки идёт сама)."""
    try:
        result = await uc.execute(project_id, body.doc_id, manual=True)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PdfPublishResponse(
        status=result.status.value,
        doc_id=result.doc_id,
        reason=result.reason.value if result.reason else None,
        error=result.code,
        message=result.detail,
        size=result.size,
    )


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
                auto_sync=body.auto_sync,
                pdf_upload=body.pdf_upload,
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


@router.post("/projects/{project_id}/git/bundle/export", response_class=FileResponse)
async def export_git_bundle(
    project_id: UUID,
    uc: FromDishka[ExportBundleUC],
    scratch: FromDishka[BundleScratch],
    body: BundleExportRequest | None = None,
) -> FileResponse:
    """Файл с веткой проекта для обмена без сервера; рабочая копия убирается после отправки."""
    password = body.password if body is not None else None
    try:
        exported = await uc.execute(
            ExportBundleInput(project_id=project_id, password=Secret(password) if password else None)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        exported.path,
        media_type="application/octet-stream",
        filename=exported.filename,
        headers={"Cache-Control": "no-store"},
        background=BackgroundTask(scratch.discard, exported.workdir),
    )


@router.post("/projects/{project_id}/git/bundle/import", response_model=OperationStartedResponse, status_code=202)
async def import_git_bundle(
    project_id: UUID,
    uc: FromDishka[ImportBundleUC],
    scratch: FromDishka[BundleScratch],
    file: UploadFile = File(...),
    password: str | None = Form(default=None),
) -> OperationStartedResponse:
    """Слияние файла с проектом тем же путём, что и ветки с сервера, но без отправки."""
    stored = await scratch.receive(file.read)
    try:
        started = await uc.execute(
            ImportBundleInput(project_id=project_id, upload=stored, password=Secret(password) if password else None)
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OperationStartedResponse(operation_id=started.operation_id)


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


@router.get("/projects/{project_id}/git/contents", response_model=GitContentsResponse)
async def get_git_contents(project_id: UUID, uc: FromDishka[GetGitContentsUC]) -> GitContentsResponse:
    """Что уйдёт в удалённый репозиторий: по локальной истории, без сети."""
    try:
        contents = await uc.execute(GetGitContentsInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return GitContentsResponse(
        files=contents.files,
        bytes=contents.bytes,
        commits=contents.commits,
        bot_authored_commits=contents.bot_authored_commits,
        signatures=contents.signatures,
        nda_files=contents.nda_files,
        pdf_tracked=contents.pdf_tracked,
        largest=[GitLargestFile(path=f.path, bytes=f.bytes) for f in contents.largest],
        over_limit=[
            GitOverLimitFile(path=f.path, bytes=f.bytes, limit=contents.limit_bytes) for f in contents.over_limit
        ],
        lfs_pointers=contents.lfs_pointers,
    )
