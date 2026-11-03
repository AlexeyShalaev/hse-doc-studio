"""git-синхронизация проекта: статус, выборка и синхронизация с удалённым репозиторием."""

from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.git_sync.fetch_remote import FetchGitRemoteInput, FetchGitRemoteUC
from hse_doc_studio.use_cases.git_sync.start_sync import StartSyncInput, StartSyncUC
from hse_doc_studio.use_cases.git_sync.status import GetGitStatusInput, GetGitStatusUC
from hse_doc_studio.use_cases.mcp.tools._base import McpTool, json_result, project_schema


class GitStatusTool(McpTool):
    spec = ToolSpec(
        name="git_status",
        description="Состояние связи проекта с git-remote: подключён ли, впереди/позади, ошибки, идущая операция.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        view = await (await self._deps.get(GetGitStatusUC)).execute(GetGitStatusInput(project_id=ctx.project_id))
        return json_result(view)


class GitFetchTool(McpTool):
    spec = ToolSpec(
        name="git_fetch",
        description="Забрать изменения из git-remote без слияния и показать, насколько проект впереди или позади.",
        parameters=project_schema({}),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        view = await (await self._deps.get(FetchGitRemoteUC)).execute(FetchGitRemoteInput(project_id=ctx.project_id))
        return json_result(view)


class GitSyncTool(McpTool):
    spec = ToolSpec(
        name="git_sync",
        description=(
            "Синхронизировать проект с git-remote (слить входящие и отправить свои снимки). Идёт в фоне: "
            "результат смотри через git_status."
        ),
        parameters=project_schema({}),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(StartSyncUC)).execute(StartSyncInput(project_id=ctx.project_id))
        return ToolResult.ok(
            localized_error(
                f"Синхронизация запущена (операция {out.operation_id}); проверь git_status.",
                f"Sync started (operation {out.operation_id}); check git_status.",
            )
        )
