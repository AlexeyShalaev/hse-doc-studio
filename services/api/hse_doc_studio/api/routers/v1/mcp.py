"""`/api/v1/mcp/*`: сведения для подключения клиента и настройки MCP локальной Студии."""

from __future__ import annotations

from fastapi import APIRouter, Request

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.mcp_views import MCP_ENDPOINT_PATH
from hse_doc_studio.api.routers import admin_mcp
from hse_doc_studio.api.schemas.mcp import McpCallItem, McpInfoResponse, McpSettingsResponse
from hse_doc_studio.core.mcp.entities import MCP_SCOPE
from hse_doc_studio.core.mcp.errors import McpError
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.mcp.list_tools import ListMcpToolsUC

router = APIRouter()


@router.get("/mcp/info", response_model=McpInfoResponse)
async def get_mcp_info(request: Request) -> McpInfoResponse:
    server = settings.mode is StudioMode.server
    uc: ListMcpToolsUC = await request.state.dishka_container.get(ListMcpToolsUC)
    try:
        tools = [e.meta.name for e in await uc.execute()]
        enabled = True
    except McpError:
        tools, enabled = [], False
    return McpInfoResponse(
        enabled=enabled,
        mode="server" if server else "local",
        endpoint_path=MCP_ENDPOINT_PATH,
        token_scope=MCP_SCOPE if server else None,
        tools=tools,
    )


# Локальная Студия: те же ручки, что в админке облака (на сервере маршруты local_only отвечают 404).
router.add_api_route("/mcp/settings", admin_mcp.get_settings, methods=["GET"], response_model=McpSettingsResponse)
router.add_api_route("/mcp/settings", admin_mcp.put_settings, methods=["PUT"], response_model=McpSettingsResponse)
router.add_api_route("/mcp/calls", admin_mcp.list_calls, methods=["GET"], response_model=list[McpCallItem])
