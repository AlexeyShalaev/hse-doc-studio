"""`/api/admin/pack-catalog*`: «Каталоги паков» установки (docs/design/template-studio.md, 10.3, срез T17).

Источники git и архив, «Проверить» (план: что появится, что мешает), «Применить» проверенной ревизии, включение и
выключение, история. Архив приходит телом запроса целиком (`application/octet-stream`), поля в строке запроса.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from hse_doc_studio.api.pack_catalog_upload import receive_archive
from hse_doc_studio.api.pack_catalog_views import (
    apply_response,
    check_response,
    event_response,
    overview_response,
    source_view_response,
)
from hse_doc_studio.api.schemas.pack_catalog import (
    ApplySourceRequest,
    CatalogApplyResponse,
    CatalogCheckResponse,
    CatalogEventResponse,
    CatalogOverviewResponse,
    CatalogSourceResponse,
    CreateGitSourceRequest,
    UpdateSourceRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.use_cases.pack_catalog.service import PackCatalogService, SourceInput

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}
_NAME_MAX = 200


async def _uc(request: Request) -> PackCatalogService:
    return await request.state.dishka_container.get(PackCatalogService)


async def get_catalog(request: Request, response: Response) -> CatalogOverviewResponse:
    response.headers.update(_NO_STORE)
    service = await _uc(request)
    return overview_response(await service.overview(require_actor()), service.limits)


async def add_git_source(request: Request, body: CreateGitSourceRequest) -> CatalogSourceResponse:
    service = await _uc(request)
    actor = require_actor()
    source = await service.add_git(
        actor,
        SourceInput(
            label=body.label,
            url=body.url,
            packs_path=body.packs_path,
            ref=body.ref,
            credential_id=body.credential_id,
            service_access_id=body.service_access_id,
            insecure_http=body.insecure_http,
            replace_builtin=body.replace_builtin,
            track=body.track,
        ),
    )
    return source_view_response(await service.source(actor, source.id))


async def add_archive_source(
    request: Request,
    name: str = Query(min_length=1, max_length=_NAME_MAX),
    label: str | None = Query(default=None, max_length=_NAME_MAX),
    packs_path: str | None = Query(default=None, max_length=512),
    replace_builtin: bool = Query(default=False),
) -> CatalogSourceResponse:
    service = await _uc(request)
    actor = require_actor()
    upload = await receive_archive(request, service.upload_path(), max_bytes=service.limits.max_archive_bytes)
    source = await service.add_archive(
        actor, upload, name=name, inp=SourceInput(label=label, packs_path=packs_path, replace_builtin=replace_builtin)
    )
    return source_view_response(await service.source(actor, source.id))


async def replace_archive(
    request: Request, source_id: UUID, name: str = Query(min_length=1, max_length=_NAME_MAX)
) -> CatalogSourceResponse:
    service = await _uc(request)
    actor = require_actor()
    await service.source(actor, source_id)
    upload = await receive_archive(request, service.upload_path(), max_bytes=service.limits.max_archive_bytes)
    await service.replace_archive(actor, source_id, upload, name=name)
    return source_view_response(await service.source(actor, source_id))


async def update_source(request: Request, source_id: UUID, body: UpdateSourceRequest) -> CatalogSourceResponse:
    service = await _uc(request)
    actor = require_actor()
    await service.update(
        actor,
        source_id,
        SourceInput(
            label=body.label,
            packs_path=body.packs_path,
            ref=body.ref,
            credential_id=body.credential_id,
            service_access_id=body.service_access_id,
            clear_access=body.clear_access,
            replace_builtin=body.replace_builtin,
            track=body.track,
        ),
    )
    if body.enabled is not None:
        await service.set_enabled(actor, source_id, body.enabled)
    return source_view_response(await service.source(actor, source_id))


async def remove_source(request: Request, source_id: UUID) -> Response:
    await (await _uc(request)).remove(require_actor(), source_id)
    return Response(status_code=204)


async def check_source(request: Request, source_id: UUID) -> CatalogCheckResponse:
    service = await _uc(request)
    actor = require_actor()
    view = await service.check(actor, source_id)
    return check_response(view, await service.source(actor, source_id))


async def apply_source(request: Request, source_id: UUID, body: ApplySourceRequest) -> CatalogApplyResponse:
    service = await _uc(request)
    actor = require_actor()
    view = await service.apply(actor, source_id, body.revision)
    return apply_response(view, await service.source(actor, source_id))


async def source_history(request: Request, source_id: UUID, response: Response) -> list[CatalogEventResponse]:
    response.headers.update(_NO_STORE)
    return [event_response(e) for e in await (await _uc(request)).history(require_actor(), source_id)]


router.add_api_route("/pack-catalog", get_catalog, methods=["GET"], response_model=CatalogOverviewResponse)
router.add_api_route(
    "/pack-catalog/sources", add_git_source, methods=["POST"], status_code=201, response_model=CatalogSourceResponse
)
router.add_api_route(
    "/pack-catalog/sources/archive",
    add_archive_source,
    methods=["POST"],
    status_code=201,
    response_model=CatalogSourceResponse,
)
router.add_api_route(
    "/pack-catalog/sources/{source_id}", update_source, methods=["PATCH"], response_model=CatalogSourceResponse
)
router.add_api_route("/pack-catalog/sources/{source_id}", remove_source, methods=["DELETE"], status_code=204)
router.add_api_route(
    "/pack-catalog/sources/{source_id}/archive", replace_archive, methods=["PUT"], response_model=CatalogSourceResponse
)
router.add_api_route(
    "/pack-catalog/sources/{source_id}/check", check_source, methods=["POST"], response_model=CatalogCheckResponse
)
router.add_api_route(
    "/pack-catalog/sources/{source_id}/apply", apply_source, methods=["POST"], response_model=CatalogApplyResponse
)
router.add_api_route(
    "/pack-catalog/sources/{source_id}/history",
    source_history,
    methods=["GET"],
    response_model=list[CatalogEventResponse],
)
