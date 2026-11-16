"""`GET /api/v1/pack-studio/.../outcome/atlas`: таблица исходов версии (срез O4, раздел 4.4 дизайна результата).

Под теми же правами, что весь раздел (`pack_studio_guard`: раздел включён, право «Автор шаблонов», область `packs`).
Читает всё и ничего не пишет. `ETag` строится из `revision` и запроса: `If-None-Match` отвечает 304 без расчёта.
Ответ сжимает общий `GZipMiddleware` (атлас ВКР: около 1 МБ JSON, около 22 КБ после gzip). Расчёт идёт в потоке под
семафором со сроком 20 с (по истечении 503 с `Retry-After`), частота 6 запросов в минуту на человека (429).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.pack_studio import pack_studio_guard
from hse_doc_studio.api.schemas.pack_studio_outcome import OutcomeStateName, PackOutcomeAtlasResponse
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.outcome.atlas import Atlas
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.use_cases.pack_studio.outcome_atlas import AtlasBusy, PackAtlasService, parse_pins

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

ATLAS_PATH = "/pack-studio/workspaces/{workspace_id}/versions/{pack}/{template}/{version}/outcome/atlas"
_CACHE = {"Cache-Control": "private, no-cache"}

IfNoneMatch = Annotated[str | None, Header(alias="If-None-Match")]


def atlas_response(
    workspace_id: UUID, pack: str, template: str, version: str, state: OutcomeStateName, atlas: Atlas
) -> PackOutcomeAtlasResponse:
    """Атлас ядра в ответ контракта: ядро и модель контракта называют поля одинаково, строгая модель проверяет."""
    return PackOutcomeAtlasResponse.model_validate(
        {
            "workspace_id": str(workspace_id),
            "pack": pack,
            "template": template,
            "version": version,
            "state": state,
            **to_json(atlas),
        }
    )


@router.get(ATLAS_PATH, response_model=PackOutcomeAtlasResponse)
async def get_atlas(  # noqa: PLR0913 — путь версии и параметры запроса
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    atlases: FromDishka[PackAtlasService],
    response: Response,
    state: OutcomeStateName = "work_tree",
    pin: Annotated[list[str] | None, Query(description="<вводная>:<значение>, повторяемый")] = None,
    example: Annotated[str | None, Query(max_length=255)] = None,
    if_none_match: IfNoneMatch = None,
) -> PackOutcomeAtlasResponse | Response:
    """Измерения, исходы и таблица `{key, outcome}`: клиент по ключу находит исход, не считая условий."""
    try:
        result = await atlases.atlas(
            require_actor(),
            workspace_id,
            pack,
            template,
            version,
            state=state,
            example=example,
            pins=parse_pins(pin or []),
            if_none_match=if_none_match,
        )
    except AtlasBusy as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": "The atlas takes too long to build. Try again in a moment."},
            headers={"Retry-After": str(exc.retry_after_s)},
        )
    headers = {"ETag": result.etag, **_CACHE}
    if result.atlas is None:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return atlas_response(workspace_id, pack, template, version, state, result.atlas)
