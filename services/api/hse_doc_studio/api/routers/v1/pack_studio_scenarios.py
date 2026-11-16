"""`/api/v1/pack-studio/.../templates/{pack}/{template}/scenarios`: сценарии шаблона (template-studio-outcome.md,
4.6 и 5, срез O6).

Сценарий это файл `<пак>/templates/<шаблон>/scenarios/<id>.yaml` рядом с `examples/`, вне каталога версии.
`GET` отдаёт список (битый файл виден с `error`), `PUT` пишет канонический YAML (без `If-Match` создаёт и отвечает
`scenario_taken`, если файл есть; с `If-Match` правит по ETag), `DELETE` удаляет файл (мягко: в git он остаётся в
истории), `POST .../run` прогоняет сценарии и сравнивает результат с ожиданием.

Единственный побочный эффект среза это запись и удаление файла сценария. Права и область токена как у всего раздела
(гард раздела), частота прогона под правилом `pack_outcome`.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import JSONResponse

from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.routers.v1.pack_studio import pack_studio_guard
from hse_doc_studio.api.schemas.pack_studio_outcome import (
    OutcomeStateName,
    PackScenarioEntry,
    PackScenarioListResponse,
    PackScenarioRunRequest,
    PackScenarioRunResponse,
    PackScenarioWriteRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.use_cases.pack_studio.outcome_service import OutcomeReply
from hse_doc_studio.use_cases.pack_studio.scenario_service import PackScenarioService, ScenarioEntry

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(pack_studio_guard)])

_SCENARIOS = "/pack-studio/workspaces/{workspace_id}/templates/{pack}/{template}/scenarios"
_REVALIDATE = {"Cache-Control": "private, no-cache"}

IfMatch = Annotated[str | None, Header(alias="If-Match")]
IfNoneMatch = Annotated[str | None, Header(alias="If-None-Match")]


def _entry_body(entry: ScenarioEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "path": entry.path,
        "etag": entry.etag,
        "scenario": to_json(entry.scenario) if entry.scenario is not None else None,
        "error": entry.error,
    }


@router.get(_SCENARIOS, response_model=PackScenarioListResponse)
async def list_scenarios(
    workspace_id: UUID,
    pack: str,
    template: str,
    scenarios: FromDishka[PackScenarioService],
    state: OutcomeStateName = "work_tree",
) -> dict[str, Any]:
    """Сценарии шаблона из рабочего дерева (`state` `head` и `base`: из коммита); битый файл виден с `error`."""
    found = await scenarios.list_scenarios(require_actor(), workspace_id, pack, template, state)
    return {
        "workspace_id": str(found.workspace_id),
        "pack": found.pack,
        "template": found.template,
        "dir": found.dir,
        "scenarios": [_entry_body(entry) for entry in found.entries],
    }


@router.put(f"{_SCENARIOS}/{{scenario_id}}", response_model=PackScenarioEntry)
async def put_scenario(  # noqa: PLR0913 — путь сценария, тело и условие записи
    workspace_id: UUID,
    pack: str,
    template: str,
    scenario_id: str,
    body: PackScenarioWriteRequest,
    scenarios: FromDishka[PackScenarioService],
    response: Response,
    if_match: IfMatch = None,
) -> dict[str, Any]:
    """Запись сценария каноническим YAML. Без `If-Match` сценария быть не должно (`scenario_taken`), с `If-Match` он
    правится по ETag файла (`stale_file`). `record_snapshot` заменяет `snapshot` текущим результатом сценария."""
    entry = await scenarios.put(
        require_actor(),
        workspace_id,
        pack,
        template,
        scenario_id,
        body.scenario.model_dump(mode="json"),
        if_match=if_match,
        record_snapshot=body.record_snapshot,
        version=body.version,
    )
    response.headers["ETag"] = entry.etag
    return _entry_body(entry)


@router.delete(f"{_SCENARIOS}/{{scenario_id}}", status_code=204, response_model=None)
async def delete_scenario(  # noqa: PLR0913 — путь сценария и условие удаления
    workspace_id: UUID,
    pack: str,
    template: str,
    scenario_id: str,
    scenarios: FromDishka[PackScenarioService],
    if_match: IfMatch = None,
) -> None:
    """Удаление файла сценария; в git он остаётся в истории, клиентская «Отмена» пишет его заново."""
    await scenarios.delete(require_actor(), workspace_id, pack, template, scenario_id, if_match=if_match)


@router.post(f"{_SCENARIOS}/run", response_model=PackScenarioRunResponse)
async def run_scenarios(  # noqa: PLR0913 — путь шаблона, тело и условный запрос
    workspace_id: UUID,
    pack: str,
    template: str,
    body: PackScenarioRunRequest,
    scenarios: FromDishka[PackScenarioService],
    if_none_match: IfNoneMatch = None,
) -> Response:
    """Прогон сценариев: результат по вводным, сравнение с утверждениями и снимком, покрытие правил. Только читает;
    `POST` из-за тела. ETag по состоянию версии и файлам сценариев, 304 по `If-None-Match`."""
    reply: OutcomeReply = await scenarios.run(
        require_actor(),
        workspace_id,
        pack,
        template,
        state=body.state,
        scenarios=body.scenarios,
        version=body.version,
        if_none_match=if_none_match,
    )
    headers = {"ETag": reply.etag, **_REVALIDATE}
    if reply.body is None:
        return Response(status_code=304, headers=headers)
    return JSONResponse(reply.body, headers=headers)
