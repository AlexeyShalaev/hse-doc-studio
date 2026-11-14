"""`/api/v1/pack-studio/*`: Студия шаблонов, срез T5 (docs/design/template-studio.md, разделы 4 и 12).

Гард раздела (`pack_studio_guard`) стоит на всех маршрутах рабочих пространств: раздел выключен (404
`pack_studio_disabled`), токен без области `packs` (403 `pack_scope_required`), нет права «Автор шаблонов» (403
`pack_studio_forbidden`). Состояние раздела (`/pack-studio/section`) открыто любому вошедшему: по нему интерфейс
решает, показывать ли раздел и переключатель в Настройках.

Файлы адресуются путём от папки паков пространства:
`files/hse-cs-sse/templates/coursework/versions/2026.1.5/version.yaml`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Request, Response

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.files import _content_type_for
from hse_doc_studio.api.schemas.pack_studio import (
    CreatePackWorkspaceRequest,
    PackFileVersionResponse,
    PackStudioSectionResponse,
    PackTreeFile,
    PackTreePack,
    PackTreeResponse,
    PackTreeTemplate,
    PackTreeVersion,
    PackWorkspaceErrorBody,
    PackWorkspaceResponse,
    PackYamlPatchRequest,
    PackYamlPatchResponse,
    ReadOnlyReason,
    UpdatePackStudioSectionRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.entities import PackTree, WorkspaceKind
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess, SectionView
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService, YamlOp
from hse_doc_studio.use_cases.pack_studio.workspaces import (
    CreateWorkspaceInput,
    PackWorkspaceService,
    WorkspaceView,
)

_NO_STORE = {"Cache-Control": "no-store"}
READ_ONLY_HEADER = "X-Pack-Read-Only"


async def pack_studio_guard(request: Request) -> None:
    container = getattr(request.state, "dishka_container", None) or request.app.state.dishka_container
    access = await container.get(PackStudioAccess)
    await access.require(require_actor())


section_router = APIRouter(route_class=SafeDishkaRoute)
router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

IfMatch = Annotated[str | None, Header(alias="If-Match")]


def section_response(view: SectionView) -> PackStudioSectionResponse:
    return PackStudioSectionResponse(
        enabled=view.enabled,
        locked=view.locked,
        allowed=view.allowed,
        has_right=view.has_right,
        standalone=view.standalone,
    )


def workspace_response(view: WorkspaceView) -> PackWorkspaceResponse:
    ws = view.workspace
    return PackWorkspaceResponse(
        id=str(ws.id),
        kind=ws.kind.value,
        label=ws.label,
        state=ws.state.value,
        busy=view.busy,
        packs_path=ws.packs_path,
        url=ws.remote_url,
        credential_id=None if ws.credential_id is None else str(ws.credential_id),
        insecure_http=ws.insecure_http,
        folder=view.folder_display,
        base_branch=ws.base_branch,
        base_sha=ws.base_sha,
        fetched_at=ws.fetched_at,
        work_branch=ws.work_branch,
        pr_url=ws.pr_url,
        pr_number=ws.pr_number,
        ci_status=ws.ci_status,
        error=None if ws.error is None else PackWorkspaceErrorBody(code=ws.error.code, detail=ws.error.detail),
        created_at=ws.created_at,
        updated_at=ws.updated_at,
    )


def tree_response(workspace_id: UUID, base_sha: str | None, tree: PackTree) -> PackTreeResponse:
    return PackTreeResponse(
        workspace_id=str(workspace_id),
        base_sha=base_sha,
        packs=[
            PackTreePack(
                id=pack.id,
                path=pack.path,
                name=dict(pack.name) if pack.name else None,
                templates=[
                    PackTreeTemplate(
                        id=template.id,
                        path=template.path,
                        name=dict(template.name) if template.name else None,
                        default_version=template.default_version,
                        versions=[
                            PackTreeVersion(
                                version=v.version,
                                path=v.path,
                                status=v.status,
                                released=v.released,
                                modified=v.modified,
                            )
                            for v in template.versions
                        ],
                    )
                    for template in pack.templates
                ],
            )
            for pack in tree.packs
        ],
        files=[
            PackTreeFile(path=f.path, is_dir=f.is_dir, size=f.size, read_only=_reason(f.read_only)) for f in tree.files
        ],
        truncated=tree.truncated,
    )


def _reason(value: str | None) -> ReadOnlyReason | None:
    if value == "version_released":
        return "version_released"
    if value == "releases_read_only":
        return "releases_read_only"
    return None


# ── раздел ──────────────────────────────────────────────────────────────────


@section_router.get("/pack-studio/section", response_model=PackStudioSectionResponse)
async def get_section(access: FromDishka[PackStudioAccess], response: Response) -> PackStudioSectionResponse:
    response.headers.update(_NO_STORE)
    return section_response(await access.view(require_actor()))


@section_router.put("/pack-studio/section", response_model=PackStudioSectionResponse)
async def put_section(
    body: UpdatePackStudioSectionRequest, access: FromDishka[PackStudioAccess]
) -> PackStudioSectionResponse:
    """Переключатель «Инструменты автора шаблонов» локальной Студии; на сервере раздел включает админ."""
    return section_response(await access.set_enabled(require_actor(), body.enabled))


# ── рабочие пространства ────────────────────────────────────────────────────


@router.get("/pack-studio/workspaces", response_model=list[PackWorkspaceResponse])
async def list_workspaces(service: FromDishka[PackWorkspaceService]) -> list[PackWorkspaceResponse]:
    return [workspace_response(view) for view in await service.list(require_actor())]


@router.post("/pack-studio/workspaces", status_code=201, response_model=PackWorkspaceResponse)
async def create_workspace(
    body: CreatePackWorkspaceRequest, service: FromDishka[PackWorkspaceService], response: Response
) -> PackWorkspaceResponse:
    """Папка готова сразу (201). Пространство над git отвечает 202 в состоянии `cloning`: клон идёт в фоне."""
    view = await service.create(
        require_actor(),
        CreateWorkspaceInput(
            kind=WorkspaceKind(body.kind),
            label=body.label,
            url=body.url,
            credential_id=body.credential_id,
            insecure_http=body.insecure_http,
            base_branch=body.base_branch,
            folder=body.folder,
            packs_path=body.packs_path,
        ),
    )
    if view.workspace.kind is WorkspaceKind.git:
        response.status_code = 202
    return workspace_response(view)


@router.get("/pack-studio/workspaces/{workspace_id}", response_model=PackWorkspaceResponse)
async def get_workspace(
    workspace_id: UUID, service: FromDishka[PackWorkspaceService], response: Response
) -> PackWorkspaceResponse:
    response.headers.update(_NO_STORE)
    return workspace_response(await service.get(require_actor(), workspace_id))


@router.delete("/pack-studio/workspaces/{workspace_id}", status_code=204, response_model=None)
async def delete_workspace(workspace_id: UUID, service: FromDishka[PackWorkspaceService]) -> None:
    await service.delete(require_actor(), workspace_id)


@router.post("/pack-studio/workspaces/{workspace_id}/refresh", status_code=202, response_model=PackWorkspaceResponse)
async def refresh_workspace(workspace_id: UUID, service: FromDishka[PackWorkspaceService]) -> PackWorkspaceResponse:
    """Выборка базовой ветки и пересчёт выпущенных версий; у неудачного или прерванного клона клон заново."""
    return workspace_response(await service.refresh(require_actor(), workspace_id))


@router.get("/pack-studio/workspaces/{workspace_id}/tree", response_model=PackTreeResponse)
async def get_tree(workspace_id: UUID, files: FromDishka[PackFilesService], response: Response) -> PackTreeResponse:
    response.headers.update(_NO_STORE)
    view = await files.tree(require_actor(), workspace_id)
    return tree_response(workspace_id, view.workspace.base_sha, view.tree)


# ── файлы ───────────────────────────────────────────────────────────────────


@router.get("/pack-studio/workspaces/{workspace_id}/files/{path:path}")
async def read_file(workspace_id: UUID, path: str, files: FromDishka[PackFilesService]) -> Response:
    """Содержимое с `ETag`; `X-Pack-Read-Only: version_released | releases_read_only`, если файл менять нельзя."""
    found = await files.read(require_actor(), workspace_id, path)
    headers = {"ETag": found.etag, **_NO_STORE}
    if found.read_only is not None:
        headers[READ_ONLY_HEADER] = found.read_only
    return Response(content=found.content, media_type=_content_type_for(found.path), headers=headers)


@router.put("/pack-studio/workspaces/{workspace_id}/files/{path:path}", response_model=PackFileVersionResponse)
async def write_file(
    workspace_id: UUID,
    path: str,
    request: Request,
    files: FromDishka[PackFilesService],
    response: Response,
    if_match: IfMatch = None,
) -> PackFileVersionResponse:
    """Файл целиком (тело запроса как есть). `If-Match` с ETag: запись только поверх той же версии."""
    content = await _body(request, files)
    written = await files.write(require_actor(), workspace_id, path, content, if_match)
    response.headers["ETag"] = written.etag
    return PackFileVersionResponse(path=written.path, etag=written.etag, size=written.size)


@router.patch("/pack-studio/workspaces/{workspace_id}/files/{path:path}", response_model=PackYamlPatchResponse)
async def patch_yaml(
    workspace_id: UUID,
    path: str,
    body: PackYamlPatchRequest,
    files: FromDishka[PackFilesService],
    response: Response,
    if_match: IfMatch = None,
) -> PackYamlPatchResponse:
    """Точечные правки YAML по пути узла (D11): остальной текст байт в байт; весь набор или ничего."""
    ops = [YamlOp(op=o.op, path=tuple(o.path), value=o.value, index=o.index, to=o.to) for o in body.ops]
    written = await files.patch_yaml(require_actor(), workspace_id, path, ops, if_match)
    response.headers["ETag"] = written.etag
    return PackYamlPatchResponse(path=written.path, etag=written.etag, size=written.size, content=written.content or "")


@router.delete("/pack-studio/workspaces/{workspace_id}/files/{path:path}", status_code=204, response_model=None)
async def delete_file(
    workspace_id: UUID, path: str, files: FromDishka[PackFilesService], if_match: IfMatch = None
) -> None:
    """Файл (с `If-Match` по желанию) или папка целиком; выпущенные версии и реестры выпусков не удаляются."""
    await files.delete(require_actor(), workspace_id, path, if_match)


async def _body(request: Request, files: PackFilesService) -> bytes:
    """Тело не длиннее предела записи: лишнее не читается в память."""
    limit = files.max_file_bytes
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise PackStudioError(PackStudioErrorCode.file_too_large, limit=limit)
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise PackStudioError(PackStudioErrorCode.file_too_large, limit=limit)
        chunks.append(chunk)
    return b"".join(chunks)
