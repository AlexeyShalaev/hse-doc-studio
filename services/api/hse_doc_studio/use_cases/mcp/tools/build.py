"""Сборки и проверки: история сборок, одна сборка с логом, отмена, прогон проверок, правила, отчёт нормоконтроля."""

from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.use_cases.checks.get_normcontrol_report import GetNormcontrolReportInput, GetNormcontrolReportUC
from hse_doc_studio.use_cases.checks.list_document_check_rules import (
    ListDocumentCheckRulesInput,
    ListDocumentCheckRulesUC,
)
from hse_doc_studio.use_cases.checks.list_project_check_rules import (
    ListProjectCheckRulesInput,
    ListProjectCheckRulesUC,
)
from hse_doc_studio.use_cases.checks.run_checks import RunChecksInput, RunChecksUC
from hse_doc_studio.use_cases.compile.cancel_compile import CancelCompileInput, CancelCompileUC
from hse_doc_studio.use_cases.compile.get_compile import GetCompileInput, GetCompileUC
from hse_doc_studio.use_cases.compile.list_compiles import ListCompilesInput, ListCompilesUC
from hse_doc_studio.use_cases.mcp.tools._base import (
    McpTool,
    bool_arg,
    int_arg,
    json_result,
    optional_text,
    project_schema,
    text_arg,
    uuid_arg,
)

_DOC = {"type": "string", "description": "Идентификатор документа, напр. vkr"}
_COMPILE = {"type": "string", "description": "Идентификатор сборки (UUID)"}


def _summary(record: CompileRecord) -> dict[str, object]:
    severities = [str(r.severity) for r in record.check_results]
    return {
        "id": record.id,
        "doc_id": record.doc_id,
        "status": record.status,
        "engine": record.engine,
        "started_at": record.started_at,
        "finished_at": record.finished_at,
        "pages": record.pages,
        "words": record.words,
        "errors": severities.count("err"),
        "warnings": severities.count("warn"),
    }


class ListCompilesTool(McpTool):
    spec = ToolSpec(
        name="list_compiles",
        description="Последние сборки документа: статус, время, страницы, число замечаний.",
        parameters=project_schema({"doc_id": _DOC, "limit": {"type": "integer", "default": 10}}, ("doc_id",)),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        doc_id = text_arg(args, "doc_id")
        limit = int_arg(args, "limit", 10, lo=1, hi=100)
        records = await (await self._deps.get(ListCompilesUC)).execute(
            ListCompilesInput(project_id=ctx.project_id, doc_id=doc_id)
        )
        records = sorted(records, key=lambda r: r.started_at, reverse=True)
        return json_result([_summary(r) for r in records[:limit]], truncated=len(records) > limit)


class GetCompileTool(McpTool):
    spec = ToolSpec(
        name="get_compile",
        description=(
            "Одна сборка: статус, страницы, замечания проверок и хвост лога (log_lines строк). PDF сборки доступен "
            "ресурсом studio://projects/{project_id}/compiles/{doc_id}/{compile_id}/pdf."
        ),
        parameters=project_schema(
            {"compile_id": _COMPILE, "log_lines": {"type": "integer", "default": 60}}, ("compile_id",)
        ),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        compile_id = uuid_arg(args, "compile_id")
        log_lines = int_arg(args, "log_lines", 60, lo=0, hi=2000)
        record = await (await self._deps.get(GetCompileUC)).execute(
            GetCompileInput(project_id=ctx.project_id, compile_id=compile_id)
        )
        if record is None:
            raise NotFoundError(str(compile_id))
        lines = (record.log or "").splitlines()
        return json_result(
            {
                **_summary(record),
                "findings": record.check_results,
                "log_tail": "\n".join(lines[-log_lines:]) if log_lines else "",
                "log_total_lines": len(lines),
            }
        )


class CancelCompileTool(McpTool):
    spec = ToolSpec(
        name="cancel_compile",
        description="Остановить идущую сборку.",
        parameters=project_schema({"compile_id": _COMPILE}, ("compile_id",)),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(CancelCompileUC)).execute(
            CancelCompileInput(project_id=ctx.project_id, compile_id=uuid_arg(args, "compile_id"))
        )
        return json_result(out)


class RunChecksTool(McpTool):
    spec = ToolSpec(
        name="run_checks",
        description=(
            "Прогнать проверки нормоконтроля по последней сборке документа без пересборки. include_external "
            "включает внешние проверки (орфография LanguageTool)."
        ),
        parameters=project_schema(
            {"doc_id": _DOC, "include_external": {"type": "boolean", "default": True}}, ("doc_id",)
        ),
    )
    kind = ToolKind.exec_

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        out = await (await self._deps.get(RunChecksUC)).execute(
            RunChecksInput(
                project_id=ctx.project_id,
                doc_id=text_arg(args, "doc_id"),
                include_external=bool_arg(args, "include_external", True),
            )
        )
        return json_result({"count": len(out.results), "results": out.results})


class ListCheckRulesTool(McpTool):
    spec = ToolSpec(
        name="list_check_rules",
        description="Правила проверок: проекта целиком или одного документа (doc_id), с действующей строгостью.",
        parameters=project_schema({"doc_id": _DOC}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        doc_id = optional_text(args, "doc_id")
        if doc_id is None:
            out = await (await self._deps.get(ListProjectCheckRulesUC)).execute(
                ListProjectCheckRulesInput(project_id=ctx.project_id)
            )
            return json_result(out.rules)
        doc_out = await (await self._deps.get(ListDocumentCheckRulesUC)).execute(
            ListDocumentCheckRulesInput(project_id=ctx.project_id, doc_id=doc_id)
        )
        return json_result(doc_out.rules)


class NormcontrolReportTool(McpTool):
    spec = ToolSpec(
        name="normcontrol_report",
        description="Сводный отчёт нормоконтроля по проекту: документы, замечания по категориям, готовность в %.",
        parameters=project_schema({}),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        report = await (await self._deps.get(GetNormcontrolReportUC)).execute(
            GetNormcontrolReportInput(project_id=ctx.project_id)
        )
        return json_result(report)
