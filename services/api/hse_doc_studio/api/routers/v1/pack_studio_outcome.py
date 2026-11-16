"""`/api/v1/pack-studio/.../outcome`: результат версии шаблона (template-studio-outcome.md, 4.6, срез O2).

`GET .../outcome/inputs?state=` отдаёт вводные версии, наборы данных и умолчания (`PackOutcomeInputs`),
`POST .../outcome` считает результат и трассу решений (`PackOutcome`), `POST .../outcome/explain` объясняет один
элемент результата: цепочку решений, соседей по правилам и «что если» (`PackOutcomeExplain`, срез O5). Всё только
читает: `POST` здесь из-за тела.
Состояния версии: `work_tree` (рабочее дерево с несохранёнными правками), `head` (последний коммит), `base`
(вершина базовой ветки); `head` и `base` читаются из git без checkout, у папки их нет (`diff_base_unavailable`).

Ответ несёт `ETag` по ключу запроса (версия, источник, `revision`, вводные); по `If-None-Match` сервер отвечает 304,
не считая. Расчёт идёт с пределом времени, при его превышении и при перегрузке 503 `outcome_busy` с `Retry-After`;
частота ограничена правилом `pack_outcome` (20 в секунду на человека, `api/rate_limit.py`).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.pack_studio import pack_studio_guard
from hse_doc_studio.api.schemas.pack_studio_outcome import (
    OutcomeStateName,
    PackOutcomeExplainRequest,
    PackOutcomeExplainResponse,
    PackOutcomeInputsResponse,
    PackOutcomeRequest,
    PackOutcomeResponse,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef
from hse_doc_studio.use_cases.pack_studio.outcome_service import (
    ExplainRequest,
    OutcomeReply,
    OutcomeRequest,
    PackOutcomeService,
)

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

_OUTCOME = "/pack-studio/workspaces/{workspace_id}/versions/{pack}/{template}/{version}/outcome"
# Ответ можно хранить, но каждый раз сверять по ETag: правка манифеста меняет ключ.
_REVALIDATE = {"Cache-Control": "private, no-cache"}

IfNoneMatch = Annotated[str | None, Header(alias="If-None-Match")]


def _respond(reply: OutcomeReply) -> Response:
    headers = {"ETag": reply.etag, **_REVALIDATE}
    if reply.body is None:
        return Response(status_code=304, headers=headers)
    return JSONResponse(reply.body, headers=headers)


@router.get(f"{_OUTCOME}/inputs", response_model=PackOutcomeInputsResponse)
async def get_outcome_inputs(  # noqa: PLR0913 — путь версии, состояние и условный запрос
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    outcome: FromDishka[PackOutcomeService],
    state: OutcomeStateName = "work_tree",
    if_none_match: IfNoneMatch = None,
) -> Response:
    """Вводные версии (из схемы версии), наборы данных и умолчания для панели «Вводные»."""
    reply = await outcome.inputs(
        require_actor(), workspace_id, pack, template, version, state, if_none_match=if_none_match
    )
    return _respond(reply)


@router.post(_OUTCOME, response_model=PackOutcomeResponse)
async def post_outcome(  # noqa: PLR0913 — путь версии, тело и условный запрос
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackOutcomeRequest,
    outcome: FromDishka[PackOutcomeService],
    if_none_match: IfNoneMatch = None,
) -> Response:
    """Результат версии для вводных: документы, поля, участники, точки сдачи, маршрут и трасса решений."""
    request = OutcomeRequest(
        state=body.state,
        scenario=body.scenario,
        example=body.example,
        inputs=body.inputs,
        include=frozenset(body.include),
    )
    reply = await outcome.outcome(
        require_actor(), workspace_id, pack, template, version, request, if_none_match=if_none_match
    )
    return _respond(reply)


@router.post(f"{_OUTCOME}/explain", response_model=PackOutcomeExplainResponse)
async def post_outcome_explain(  # noqa: PLR0913 — путь версии, тело и условный запрос
    workspace_id: UUID,
    pack: str,
    template: str,
    version: str,
    body: PackOutcomeExplainRequest,
    outcome: FromDishka[PackOutcomeService],
    if_none_match: IfNoneMatch = None,
) -> Response:
    """«Почему?» элемента: цепочка решений от условий до исхода, соседние элементы и «что если» по вводным."""
    request = ExplainRequest(
        element=ElementRef(body.element.section, body.element.id),
        state=body.state,
        scenario=body.scenario,
        example=body.example,
        inputs=body.inputs,
    )
    reply = await outcome.explain(
        require_actor(), workspace_id, pack, template, version, request, if_none_match=if_none_match
    )
    return _respond(reply)
