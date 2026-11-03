"""`/api/admin/mcp/*`: включение MCP, тулы и группы, журнал вызовов (docs/design/mcp.md, раздел 4)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, Response

from hse_doc_studio.api.mcp_views import call_item, settings_change, settings_response
from hse_doc_studio.api.schemas.mcp import (
    McpCallItem,
    McpCallOutcomeName,
    McpSettingsResponse,
    UpdateMcpSettingsRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.mcp.entities import McpCallOutcome, McpCallQuery
from hse_doc_studio.use_cases.mcp.journal import ListMcpCallsUC
from hse_doc_studio.use_cases.mcp.settings import GetMcpSettingsUC, UpdateMcpSettingsUC

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


async def get_settings(request: Request, response: Response) -> McpSettingsResponse:
    response.headers.update(_NO_STORE)
    return settings_response(await (await _uc(request, GetMcpSettingsUC)).execute(require_actor()))


async def put_settings(request: Request, body: UpdateMcpSettingsRequest) -> McpSettingsResponse:
    try:
        view = await (await _uc(request, UpdateMcpSettingsUC)).execute(require_actor(), settings_change(body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return settings_response(view)


async def list_calls(
    request: Request,
    response: Response,
    tool: str | None = Query(default=None, max_length=128),
    actor_id: str | None = Query(default=None, max_length=64),
    outcome: McpCallOutcomeName | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[McpCallItem]:
    response.headers.update(_NO_STORE)
    query = McpCallQuery(
        tool=tool, actor_id=actor_id, outcome=McpCallOutcome(outcome) if outcome else None, limit=limit
    )
    records = await (await _uc(request, ListMcpCallsUC)).execute(require_actor(), query)
    return [call_item(r) for r in records]


router.add_api_route("/mcp/settings", get_settings, methods=["GET"], response_model=McpSettingsResponse)
router.add_api_route("/mcp/settings", put_settings, methods=["PUT"], response_model=McpSettingsResponse)
router.add_api_route("/mcp/calls", list_calls, methods=["GET"], response_model=list[McpCallItem])
