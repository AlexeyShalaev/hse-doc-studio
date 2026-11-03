"""`hse-doc-studio mcp`: мост stdio ↔ Streamable HTTP к работающей Студии (docs/design/mcp.md, M13).

Клиенты, которые запускают MCP-сервер процессом (stdin/stdout), получают те же тулы, ресурсы и prompts, что
по HTTP: мост пересылает каждый запрос на `/mcp` Студии и отдаёт ответ как есть. Своих тулов у моста нет, поэтому
нет и второго процесса, пишущего в те же проекты. По умолчанию адрес локальной Студии; для облака `--url` и токен
(`--token` или `HSE_STUDIO_TOKEN`).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
import mcp_types as types
from mcp.client.client import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.context import ServerRequestContext
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

TOKEN_ENV = "HSE_STUDIO_TOKEN"  # noqa: S105 — имя переменной, не секрет
DEFAULT_URL = "http://127.0.0.1:17240/mcp"
_TIMEOUT_S = 300.0


def endpoint(url: str) -> str:
    """Адрес Студии или сразу `/mcp`: `https://studio.example` и `https://studio.example/mcp` равноценны."""
    base = url.rstrip("/")
    return base if base.endswith("/mcp") else f"{base}/mcp"


def headers_for(token: str | None, language: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if language in {"ru", "en"}:
        headers["X-Interface-Language"] = language
    return headers


class Bridge:
    """Пересылка запросов: на каждый запрос своё подключение (сервер Студии без состояния)."""

    def __init__(self, url: str, headers: dict[str, str], http: httpx2.AsyncClient | None = None) -> None:
        self._url = endpoint(url)
        self._headers = headers
        self._http = http

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[Client]:
        if self._http is not None:
            async with Client(streamable_http_client(self._url, http_client=self._http), mode="legacy") as client:
                yield client
            return
        async with (
            httpx2.AsyncClient(headers=self._headers, timeout=_TIMEOUT_S) as http,
            Client(streamable_http_client(self._url, http_client=http), mode="legacy") as client,
        ):
            yield client

    async def list_tools(
        self, _: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        async with self._client() as c:
            return await c.list_tools(cursor=params.cursor if params else None)

    async def call_tool(
        self, _: ServerRequestContext[Any, Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        async with self._client() as c:
            return await c.call_tool(params.name, dict(params.arguments or {}))

    async def list_resources(
        self, _: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListResourcesResult:
        async with self._client() as c:
            return await c.list_resources(cursor=params.cursor if params else None)

    async def list_resource_templates(
        self, _: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListResourceTemplatesResult:
        async with self._client() as c:
            return await c.list_resource_templates(cursor=params.cursor if params else None)

    async def read_resource(
        self, _: ServerRequestContext[Any, Any], params: types.ReadResourceRequestParams
    ) -> types.ReadResourceResult:
        async with self._client() as c:
            return await c.read_resource(str(params.uri))

    async def list_prompts(
        self, _: ServerRequestContext[Any, Any], params: types.PaginatedRequestParams | None
    ) -> types.ListPromptsResult:
        async with self._client() as c:
            return await c.list_prompts(cursor=params.cursor if params else None)

    async def get_prompt(
        self, _: ServerRequestContext[Any, Any], params: types.GetPromptRequestParams
    ) -> types.GetPromptResult:
        async with self._client() as c:
            return await c.get_prompt(params.name, dict(params.arguments or {}))

    def server(self, version: str) -> Server[Any]:
        return Server(
            "hse-doc-studio",
            version=version,
            title="HSE Doc Studio",
            on_list_tools=self.list_tools,
            on_call_tool=self.call_tool,
            on_list_resources=self.list_resources,
            on_list_resource_templates=self.list_resource_templates,
            on_read_resource=self.read_resource,
            on_list_prompts=self.list_prompts,
            on_get_prompt=self.get_prompt,
        )


async def run_bridge(url: str, token: str | None, language: str | None, version: str) -> None:
    bridge = Bridge(url, headers_for(token or os.environ.get(TOKEN_ENV), language))
    server = bridge.server(version)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def run_cli(url: str | None, token: str | None, language: str | None) -> int:
    """Точка входа `hse-doc-studio mcp`; stdout занят протоколом, поэтому сообщения только в stderr."""
    import anyio  # noqa: PLC0415

    from hse_doc_studio import __version__  # noqa: PLC0415

    anyio.run(run_bridge, url or DEFAULT_URL, token, language, __version__)
    return 0
