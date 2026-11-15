"""`/api/v1/pack-studio/workspaces/{id}/catalog*`: «Подключить к каталогу этой Студии» (template-studio.md, 10.3).

Только локально и только у пространства над папкой: папка становится источником каталога (вид `folder`), её
выпущенные версии после «Применить» появляются в мастере проекта. Тот же конвейер, что у «Каталогов паков» в
админке сервера: проверка лоадером этой Студии, `pack_lint`, `releases check`, хранилище по дайджесту.
"""

from __future__ import annotations

from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Response

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.pack_catalog_views import apply_response, check_response, source_view_response
from hse_doc_studio.api.routers.v1.pack_studio import pack_studio_guard
from hse_doc_studio.api.schemas.pack_catalog import (
    ApplySourceRequest,
    CatalogApplyResponse,
    CatalogCheckResponse,
    UpdateSourceRequest,
    WorkspaceCatalogCheckRequest,
    WorkspaceCatalogResponse,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.pack_catalog.entities import CatalogSource
from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode
from hse_doc_studio.core.pack_studio.entities import WorkspaceKind
from hse_doc_studio.use_cases.pack_catalog.service import PackCatalogService, SourceInput
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

_BASE = "/pack-studio/workspaces/{workspace_id}/catalog"
_NO_STORE = {"Cache-Control": "no-store"}


async def _folder_source(
    actor: Actor, workspace_id: UUID, workspaces: PackWorkspaceService, catalog: PackCatalogService
) -> CatalogSource | None:
    view = await workspaces.get(actor, workspace_id)
    if view.workspace.kind is not WorkspaceKind.folder:
        raise CatalogError(CatalogErrorCode.source_kind_not_allowed)
    return await catalog.find_folder_source(actor, workspace_id)


async def _required(
    actor: Actor, workspace_id: UUID, workspaces: PackWorkspaceService, catalog: PackCatalogService
) -> CatalogSource:
    source = await _folder_source(actor, workspace_id, workspaces, catalog)
    if source is None:
        raise CatalogError(CatalogErrorCode.source_not_found)
    return source


@router.get(_BASE, response_model=WorkspaceCatalogResponse)
async def get_workspace_catalog(
    workspace_id: UUID,
    workspaces: FromDishka[PackWorkspaceService],
    catalog: FromDishka[PackCatalogService],
    response: Response,
) -> WorkspaceCatalogResponse:
    response.headers.update(_NO_STORE)
    actor = require_actor()
    source = await _folder_source(actor, workspace_id, workspaces, catalog)
    if source is None:
        return WorkspaceCatalogResponse(source=None)
    return WorkspaceCatalogResponse(source=source_view_response(await catalog.source(actor, source.id)))


@router.post(f"{_BASE}/check", response_model=CatalogCheckResponse)
async def check_workspace_catalog(
    workspace_id: UUID,
    body: WorkspaceCatalogCheckRequest,
    workspaces: FromDishka[PackWorkspaceService],
    catalog: FromDishka[PackCatalogService],
) -> CatalogCheckResponse:
    """Папка подключается при первой проверке (источник `folder`), дальше проверка берёт её свежий снимок."""
    actor = require_actor()
    source = await _folder_source(actor, workspace_id, workspaces, catalog)
    if source is None:
        ws = (await workspaces.get(actor, workspace_id)).workspace
        source = await catalog.add_folder(
            actor, folder=ws.folder or "", packs_path=ws.packs_path, label=ws.label, workspace_id=ws.id
        )
    if source.replace_builtin != body.replace_builtin:
        source = await catalog.update(actor, source.id, SourceInput(replace_builtin=body.replace_builtin))
    view = await catalog.check(actor, source.id)
    return check_response(view, await catalog.source(actor, source.id))


@router.post(f"{_BASE}/apply", response_model=CatalogApplyResponse)
async def apply_workspace_catalog(
    workspace_id: UUID,
    body: ApplySourceRequest,
    workspaces: FromDishka[PackWorkspaceService],
    catalog: FromDishka[PackCatalogService],
) -> CatalogApplyResponse:
    actor = require_actor()
    source = await _required(actor, workspace_id, workspaces, catalog)
    if not source.enabled:
        source = await catalog.set_enabled(actor, source.id, True)
    view = await catalog.apply(actor, source.id, body.revision)
    return apply_response(view, await catalog.source(actor, source.id))


@router.patch(_BASE, response_model=WorkspaceCatalogResponse)
async def update_workspace_catalog(
    workspace_id: UUID,
    body: UpdateSourceRequest,
    workspaces: FromDishka[PackWorkspaceService],
    catalog: FromDishka[PackCatalogService],
) -> WorkspaceCatalogResponse:
    """Только включение и выключение: выключенная папка прячет свои паки из мастера, версии остаются."""
    actor = require_actor()
    source = await _required(actor, workspace_id, workspaces, catalog)
    if body.enabled is not None:
        await catalog.set_enabled(actor, source.id, body.enabled)
    return WorkspaceCatalogResponse(source=source_view_response(await catalog.source(actor, source.id)))


@router.delete(_BASE, status_code=204)
async def disconnect_workspace_catalog(
    workspace_id: UUID,
    workspaces: FromDishka[PackWorkspaceService],
    catalog: FromDishka[PackCatalogService],
) -> Response:
    actor = require_actor()
    source = await _required(actor, workspace_id, workspaces, catalog)
    await catalog.remove(actor, source.id)
    return Response(status_code=204)
