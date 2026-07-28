from __future__ import annotations

import mimetypes
from uuid import UUID

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response

from hse_doc_studio.api.schemas.file import (
    CreateDirRequest,
    FileTreeItemResponse,
    FileVersionResponse,
    MoveFileRequest,
)
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.use_cases.files.create_dir import CreateDirInput, CreateDirUC
from hse_doc_studio.use_cases.files.delete_file import DeleteFileInput, DeleteFileUC
from hse_doc_studio.use_cases.files.get_file import GetFileInput, GetFileUC
from hse_doc_studio.use_cases.files.get_file_version import (
    GetFileVersionInput,
    GetFileVersionUC,
)
from hse_doc_studio.use_cases.files.list_file_tree import (
    ListFileTreeInput,
    ListFileTreeUC,
)
from hse_doc_studio.use_cases.files.move_file import MoveFileInput, MoveFileUC
from hse_doc_studio.use_cases.files.put_file import PutFileInput, PutFileUC, StaleFileError

router = APIRouter(route_class=DishkaRoute)

_EXTENSION_CONTENT_TYPES: dict[str, str] = {
    ".tex": "text/plain; charset=utf-8",
    ".bib": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json",
    ".yaml": "text/yaml; charset=utf-8",
    ".yml": "text/yaml; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript",
    ".zip": "application/zip",
}


def _content_type_for(filename: str) -> str:
    lower = filename.lower()
    for ext, ct in _EXTENSION_CONTENT_TYPES.items():
        if lower.endswith(ext):
            return ct
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


@router.get(
    "/projects/{project_id}/files",
    response_model=list[FileTreeItemResponse],
)
async def list_file_tree(
    project_id: UUID,
    uc: FromDishka[ListFileTreeUC],
) -> list[FileTreeItemResponse]:
    try:
        result = await uc.execute(ListFileTreeInput(project_id=project_id))
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [
        FileTreeItemResponse(
            path=item.path,
            size=item.size,
            modified_at=item.modified_at,
            deletable=item.deletable,
            is_dir=item.is_dir,
        )
        for item in result.items
    ]


@router.get("/projects/{project_id}/files/{path:path}")
async def get_file(
    project_id: UUID,
    path: str,
    uc: FromDishka[GetFileUC],
) -> Response:
    try:
        result = await uc.execute(GetFileInput(project_id=project_id, path=path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    content_type = _content_type_for(result.filename)
    # ETag — версия, на которую клиент будет ссылаться при сохранении (`If-Match`).
    # Без неё Студия молча затирала правку, сделанную снаружи (VS Code и т.п.).
    return Response(
        content=result.content,
        media_type=content_type,
        headers={"ETag": file_etag(result.content)},
    )


@router.get(
    "/projects/{project_id}/file-version/{path:path}",
    response_model=FileVersionResponse,
)
async def get_file_version(
    project_id: UUID,
    path: str,
    uc: FromDishka[GetFileVersionUC],
) -> FileVersionResponse:
    """Версия файла без содержимого — открытые вкладки опрашивают её на изменения."""
    try:
        result = await uc.execute(GetFileVersionInput(project_id=project_id, path=path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileVersionResponse(etag=result.etag, size=result.size)


@router.put(
    "/projects/{project_id}/files/{path:path}",
    status_code=204,
    response_model=None,
)
async def put_file(
    project_id: UUID,
    path: str,
    request: Request,
    uc: FromDishka[PutFileUC],
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> None:
    content = await request.body()
    try:
        result = await uc.execute(PutFileInput(project_id=project_id, path=path, content=content, if_match=if_match))
    except StaleFileError as exc:
        # 409, а не 412: клиенту нужен не только отказ, но и текущее содержимое —
        # интерфейс предлагает «взять с диска / оставить своё» прямо на месте.
        raise HTTPException(
            status_code=409,
            detail={
                "code": "stale_file",
                "etag": exc.current_etag,
                "content": exc.current_content.decode("utf-8", errors="replace"),
            },
        ) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    response.headers["ETag"] = result.etag


@router.post(
    "/projects/{project_id}/file-ops/move",
    status_code=204,
    response_model=None,
)
async def move_file(
    project_id: UUID,
    body: MoveFileRequest,
    uc: FromDishka[MoveFileUC],
) -> None:
    try:
        await uc.execute(MoveFileInput(project_id=project_id, src=body.src, dst=body.dst))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/file-ops/mkdir",
    status_code=204,
    response_model=None,
)
async def create_dir(
    project_id: UUID,
    body: CreateDirRequest,
    uc: FromDishka[CreateDirUC],
) -> None:
    try:
        await uc.execute(CreateDirInput(project_id=project_id, path=body.path))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.delete(
    "/projects/{project_id}/files/{path:path}",
    status_code=204,
    response_model=None,
)
async def delete_file(
    project_id: UUID,
    path: str,
    uc: FromDishka[DeleteFileUC],
) -> None:
    try:
        await uc.execute(DeleteFileInput(project_id=project_id, path=path))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
