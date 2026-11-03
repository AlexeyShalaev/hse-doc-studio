"""Сдача и подписи: только чтение. Пакет сдачи собирает тул агента package_project; подписание не выставляется."""

from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.use_cases.mcp.tools._base import McpTool, json_result, project_schema
from hse_doc_studio.use_cases.signatures.get_signatures import GetSignaturesInput, GetSignaturesUC
from hse_doc_studio.use_cases.submission.get_submission_profiles import (
    GetSubmissionProfilesInput,
    GetSubmissionProfilesUC,
)
from hse_doc_studio.use_cases.submission.list_submissions import ListSubmissionsInput, ListSubmissionsUC


class ListSubmissionProfilesTool(McpTool):
    spec = ToolSpec(
        name="list_submission_profiles",
        description="Профили сдачи проекта (куда и какой комплект документов сдаётся) для package_project.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(GetSubmissionProfilesUC)).execute(
            GetSubmissionProfilesInput(project_id=ctx.project_id)
        )
        return json_result(out.profiles)


class ListSubmissionsTool(McpTool):
    spec = ToolSpec(
        name="list_submissions",
        description="Собранные пакеты сдачи: когда, по какому профилю, размер.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(ListSubmissionsUC)).execute(ListSubmissionsInput(project_id=ctx.project_id))
        return json_result(
            [{"record": i.record, "size_bytes": i.size_bytes, "profile_name": i.profile_name} for i in out.items]
        )


class ListSignaturesTool(McpTool):
    spec = ToolSpec(
        name="list_signatures",
        description="Состояние подписей документов: какие слоты подписаны, какие ждут, устаревшие заморозки.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(GetSignaturesUC)).execute(GetSignaturesInput(project_id=ctx.project_id))
        return json_result({"state": out.state, "stale_frozen": out.stale_frozen, "plate_outdated": out.plate_outdated})
