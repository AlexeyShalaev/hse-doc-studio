"""MCP-сервер Студии на `/mcp`: Streamable HTTP без состояния поверх официального SDK (docs/design/mcp.md).

Обёртка `McpEndpoint` устанавливает актора: в облаке только персональный токен с областью `mcp` (cookie не
принимаются, поэтому CSRF к адресу неприменим), локально единственный актор и проверка Host/Origin против
DNS-rebinding. Каждый запрос получает свой менеджер SDK в режиме без состояния: ему не нужен общий жизненный
цикл приложения, а реплики api не делят сессии. Обработчики SDK открывают контейнер запроса dishka и вызывают
сценарии `use_cases/mcp`; актор и язык ставятся в contextvars заново, так как задача SDK может жить отдельно.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import mcp_types as types
import structlog
from dishka import AsyncContainer
from fastapi import FastAPI
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.shared.exceptions import MCPError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from hse_doc_studio.api.auth_cookie import bearer_token
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.local_host_guard import _hostname, trusted_local_hosts
from hse_doc_studio.api.mcp_views import MCP_ENDPOINT_PATH
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.identity.entities import ActorCredentials
from hse_doc_studio.core.identity.protocols import IActorResolver
from hse_doc_studio.core.mcp.entities import MCP_SCOPE
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode, default_message
from hse_doc_studio.core.mcp.protocols import IMcpSettingsStore
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.rate_limit import IRateLimiter, RateDecision, RateRule
from hse_doc_studio.use_cases.mcp.call_tool import CallMcpToolUC
from hse_doc_studio.use_cases.mcp.catalog import McpToolEntry
from hse_doc_studio.use_cases.mcp.list_tools import ListMcpToolsUC
from hse_doc_studio.use_cases.mcp.prompts import MCP_PROMPTS, get_prompt
from hse_doc_studio.use_cases.mcp.resources import PROJECTS_URI, RESOURCE_TEMPLATES, ReadMcpResourceUC

logger = structlog.get_logger(__name__)

_STATE_ACTOR = "mcp_actor"
_STATE_LANG = "mcp_lang"
_REALM = 'Bearer realm="hse-doc-studio"'
# Коды JSON-RPC для отказов вне тулов (ресурсы, prompts): «не найдено» и «нет прав» по соглашению MCP.
_RESOURCE_NOT_FOUND = -32002
_FORBIDDEN = -32003


class _ScaledLimiter:
    """Ограничитель приложения с тем же масштабом правил, что у `/api/v1` (`rate_limit.scale`)."""

    def __init__(self, limiter: IRateLimiter, scale: float) -> None:
        self._limiter = limiter
        self._scale = scale

    async def hit(self, rule: RateRule, key: str) -> RateDecision:
        if self._scale != 1.0:
            rule = RateRule(rule.name, max(1, round(rule.limit * self._scale)), rule.window_s)
        return await self._limiter.hit(rule, key)


def _limiter(request: Request) -> IRateLimiter | None:
    limiter: IRateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return None
    return _ScaledLimiter(limiter, float(getattr(request.app.state, "rate_limit_scale", 1.0)))


def _annotations(entry: McpToolEntry) -> types.ToolAnnotations:
    meta = entry.meta
    return types.ToolAnnotations(
        read_only_hint=meta.read_only,
        destructive_hint=meta.dangerous,
        idempotent_hint=meta.read_only,
        open_world_hint=False,
    )


def _tool(entry: McpToolEntry) -> types.Tool:
    return types.Tool(
        name=entry.spec.name,
        description=entry.spec.description,
        input_schema=entry.spec.parameters,
        annotations=_annotations(entry),
    )


def _rpc_error(exc: McpError) -> MCPError:
    if exc.code in {McpErrorCode.not_found, McpErrorCode.unknown_tool}:
        return MCPError(_RESOURCE_NOT_FOUND, str(exc))
    if exc.code is McpErrorCode.invalid_arguments:
        return MCPError(types.INVALID_PARAMS, str(exc))
    if exc.code is McpErrorCode.failed:
        return MCPError(types.INTERNAL_ERROR, str(exc))
    if exc.code is McpErrorCode.server_restarting:
        return MCPError(types.INTERNAL_ERROR, str(exc), {"code": exc.code.value, "retry_after_s": exc.retry_after_s})
    return MCPError(_FORBIDDEN, str(exc), {"code": exc.code.value})


@asynccontextmanager
async def _request_scope(ctx: ServerRequestContext[Any, Any]) -> AsyncIterator[tuple[AsyncContainer, Request]]:
    """Актор и язык из обёртки, контейнер запроса dishka."""
    request = ctx.request
    if not isinstance(request, Request):
        raise MCPError(types.INTERNAL_ERROR, "MCP is served over HTTP only")
    actor = request.scope.get("state", {}).get(_STATE_ACTOR)
    if not isinstance(actor, Actor):
        raise MCPError(_FORBIDDEN, default_message(McpErrorCode.forbidden))
    set_current_actor(actor)
    set_interface_language(request.scope.get("state", {}).get(_STATE_LANG))
    root: AsyncContainer = request.app.state.dishka_container
    async with root(context={Request: request}) as container:
        yield container, request


async def _list_tools(
    ctx: ServerRequestContext[Any, Any], _: types.PaginatedRequestParams | None
) -> types.ListToolsResult:
    async with _request_scope(ctx) as (container, _request):
        try:
            entries = await (await container.get(ListMcpToolsUC)).execute()
        except McpError as exc:
            raise _rpc_error(exc) from exc
    return types.ListToolsResult(tools=[_tool(e) for e in entries])


async def _call_tool(ctx: ServerRequestContext[Any, Any], params: types.CallToolRequestParams) -> types.CallToolResult:
    async with _request_scope(ctx) as (container, request):
        uc = await container.get(CallMcpToolUC)
        out = await uc.execute(
            params.name,
            dict(params.arguments or {}),
            client=request.headers.get("user-agent"),
            limiter=_limiter(request),
        )
    meta: dict[str, Any] | None = None
    if out.error_code is not None:
        meta = {"code": out.error_code.value}
        if out.retry_after_s is not None:
            meta["retry_after_s"] = out.retry_after_s
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=out.result.text)],
        is_error=out.result.is_error,
        meta=meta,
    )


async def _list_resources(
    ctx: ServerRequestContext[Any, Any], _: types.PaginatedRequestParams | None
) -> types.ListResourcesResult:
    return types.ListResourcesResult(
        resources=[
            types.Resource(
                uri=PROJECTS_URI, name="projects", description="Проекты Студии", mime_type="application/json"
            )
        ]
    )


async def _list_resource_templates(
    ctx: ServerRequestContext[Any, Any], _: types.PaginatedRequestParams | None
) -> types.ListResourceTemplatesResult:
    return types.ListResourceTemplatesResult(
        resource_templates=[
            types.ResourceTemplate(
                uri_template=t.uri_template, name=t.name, description=t.description, mime_type=t.mime_type
            )
            for t in RESOURCE_TEMPLATES
        ]
    )


async def _read_resource(
    ctx: ServerRequestContext[Any, Any], params: types.ReadResourceRequestParams
) -> types.ReadResourceResult:
    uri = str(params.uri)
    async with _request_scope(ctx) as (container, request):
        try:
            content = await (await container.get(ReadMcpResourceUC)).execute(uri, limiter=_limiter(request))
        except McpError as exc:
            raise _rpc_error(exc) from exc
    if content.blob is not None:
        blob = base64.b64encode(content.blob).decode("ascii")
        return types.ReadResourceResult(
            contents=[types.BlobResourceContents(uri=uri, mime_type=content.mime_type, blob=blob)]
        )
    return types.ReadResourceResult(
        contents=[types.TextResourceContents(uri=uri, mime_type=content.mime_type, text=content.text or "")]
    )


async def _list_prompts(
    ctx: ServerRequestContext[Any, Any], _: types.PaginatedRequestParams | None
) -> types.ListPromptsResult:
    return types.ListPromptsResult(
        prompts=[
            types.Prompt(
                name=p.name,
                description=p.description,
                arguments=[
                    types.PromptArgument(name=a.name, description=a.description, required=a.required)
                    for a in p.arguments
                ],
            )
            for p in MCP_PROMPTS
        ]
    )


async def _get_prompt(
    ctx: ServerRequestContext[Any, Any], params: types.GetPromptRequestParams
) -> types.GetPromptResult:
    async with _request_scope(ctx):
        try:
            prompt = get_prompt(params.name)
            text = prompt.render(dict(params.arguments or {}))
        except McpError as exc:
            raise _rpc_error(exc) from exc
    return types.GetPromptResult(
        description=prompt.description,
        messages=[types.PromptMessage(role="user", content=types.TextContent(type="text", text=text))],
    )


def build_mcp_server() -> Server[Any]:
    return Server(
        "hse-doc-studio",
        version=settings.get_app_version(),
        title="HSE Doc Studio",
        instructions=(
            "Инструменты HSE Doc Studio: проекты ВКР и курсовых на LaTeX, файлы, сборка PDF, нормоконтроль, "
            "история и сдача. Начни с list_projects; тулы проекта принимают project_id."
        ),
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
        on_list_resources=_list_resources,
        on_list_resource_templates=_list_resource_templates,
        on_read_resource=_read_resource,
        on_list_prompts=_list_prompts,
        on_get_prompt=_get_prompt,
    )


def _json(status: int, code: str, detail: str, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail, "code": code}, status_code=status, headers=headers)


class McpEndpoint:
    """ASGI-приложение `/mcp`: актор, включённость и передача запроса SDK."""

    def __init__(self, server: Server[Any] | None = None, *, mode: StudioMode | None = None) -> None:
        self._server = server or build_mcp_server()
        self._mode = mode

    @property
    def mode(self) -> StudioMode:
        return self._mode or settings.mode

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return
        request = Request(scope, receive)
        actor_or_response = await self._actor(request)
        if isinstance(actor_or_response, JSONResponse):
            await actor_or_response(scope, receive, send)
            return
        container: AsyncContainer = request.app.state.dishka_container
        if not (await (await container.get(IMcpSettingsStore)).get()).enabled:
            set_interface_language(request.headers.get("x-interface-language"))
            await _json(503, McpErrorCode.mcp_disabled.value, default_message(McpErrorCode.mcp_disabled))(
                scope, receive, send
            )
            return
        state = scope.setdefault("state", {})
        state[_STATE_ACTOR] = actor_or_response
        state[_STATE_LANG] = request.headers.get("x-interface-language") or _accept_language(request)
        manager = StreamableHTTPSessionManager(app=self._server, stateless=True, json_response=True)
        async with manager.run():
            await manager.handle_request(scope, receive, send)

    async def _actor(self, request: Request) -> Actor | JSONResponse:
        if self.mode is StudioMode.local:
            return self._local_actor(request)
        token = bearer_token(request)
        if not token:
            return _json(401, "auth_required", "Bearer token required", {"WWW-Authenticate": _REALM})
        container: AsyncContainer = request.app.state.dishka_container
        resolver = await container.get(IActorResolver)
        actor = await resolver.resolve(ActorCredentials(session_secret=None, bearer_token=token, guest_secret=None))
        if actor is None or actor.source is not ActorSource.pat:
            return _json(
                401,
                "invalid_token",
                "The access token is invalid, expired or revoked",
                {"WWW-Authenticate": f'{_REALM}, error="invalid_token"'},
            )
        if MCP_SCOPE not in actor.scopes:
            return _json(
                403,
                "insufficient_scope",
                f"The token has no {MCP_SCOPE} scope",
                {"WWW-Authenticate": f'{_REALM}, error="insufficient_scope", scope="{MCP_SCOPE}"'},
            )
        return actor

    @staticmethod
    def _local_actor(request: Request) -> Actor | JSONResponse:
        """Локально токена нет: страница с перепривязанным на 127.0.0.1 именем выдаёт себя Host и Origin."""
        trusted = trusted_local_hosts()
        host = _hostname(request.headers.get("host", ""))
        origin = request.headers.get("origin")
        if host not in trusted or (origin is not None and _hostname(origin) not in trusted):
            return _json(403, "forbidden", "Untrusted Host or Origin")
        return Actor.local()


def _accept_language(request: Request) -> str | None:
    raw = request.headers.get("accept-language", "")
    first = raw.split(",", 1)[0].strip().lower()
    return "en" if first.startswith("en") else "ru" if first.startswith("ru") else None


def install_mcp(app: FastAPI, *, mode: StudioMode | None = None) -> None:
    """Маршрут `/mcp` до SPA-фолбэка; GET (поток уведомлений) в режиме без состояния SDK отклоняет сам."""
    app.router.routes.append(
        Route(MCP_ENDPOINT_PATH, endpoint=McpEndpoint(mode=mode), methods=["GET", "POST", "DELETE"])
    )


__all__ = ["McpEndpoint", "build_mcp_server", "install_mcp"]
