from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.value_objects import CheckResult
from hse_doc_studio.use_cases.checks.get_check_results import GetCheckResultsInput, GetCheckResultsUC

_SPEC = ToolSpec(
    name="list_check_findings",
    description=(
        "Замечания последней сборки документа (ГОСТ/ЕСПД-проверки и LanguageTool): "
        "правило, важность, сообщение и место (файл:строка)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "Идентификатор документа, напр. vkr, tz, pmi"},
        },
        "required": ["doc_id"],
    },
)


class ListCheckFindingsTool:
    def __init__(self, get_check_results_uc: GetCheckResultsUC) -> None:
        self._get_results = get_check_results_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        doc_id = str(args.get("doc_id", "")).strip()
        if not doc_id:
            return ToolResult.error("provide the doc_id parameter" if lang == Lang.en else "укажите параметр doc_id")
        try:
            out = await self._get_results.execute(GetCheckResultsInput(project_id=ctx.project_id, doc_id=doc_id))
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))
        if out.compile_id is None:
            return ToolResult.ok(
                f"document {doc_id} has not been built yet — compile it first"
                if lang == Lang.en
                else f"для документа {doc_id} ещё нет сборки — сначала скомпилируйте его"
            )
        if not out.results:
            return ToolResult.ok(
                f"no findings: document {doc_id} passed the checks"
                if lang == Lang.en
                else f"замечаний нет: документ {doc_id} прошёл проверки"
            )
        header = (
            f"Findings for {doc_id} ({len(out.results)}):\n"
            if lang == Lang.en
            else f"Замечания для {doc_id} ({len(out.results)}):\n"
        )
        return ToolResult.ok(header + "\n".join(_format(r) for r in out.results))


def _format(result: CheckResult) -> str:
    where = ""
    if result.location is not None:
        line = f":{result.location.line}" if result.location.line is not None else ""
        where = f" [{result.location.file}{line}]"
    return f"- {result.severity} {result.rule_id}: {result.message}{where}"
