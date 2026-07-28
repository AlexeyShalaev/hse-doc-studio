from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.chat.tools._requirements_format import describe_format, summarize_matrix
from hse_doc_studio.use_cases.requirements.get_requirements import (
    GetRequirementsInput,
    GetRequirementsUC,
)

_SPEC = ToolSpec(
    name="trace_requirements",
    description=(
        "Матрица трассировки требований проекта: идентификатор, где определено, где "
        "используется, и статус (ok / warn — не используется / err — не определено). "
        "Показывает активный формат распознавания — настроить его помогают "
        "preview_requirements_format и set_requirements_format."
    ),
    parameters={"type": "object", "properties": {}},
)


class TraceRequirementsTool:
    def __init__(self, get_requirements_uc: GetRequirementsUC) -> None:
        self._get_requirements = get_requirements_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:  # noqa: ARG002 — no args
        lang = current_interface_language()
        try:
            out = await self._get_requirements.execute(GetRequirementsInput(project_id=ctx.project_id))
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))
        if lang == Lang.en:
            scope = "project" if out.overridden else "from template"
            header = f"Detection format ({scope}): {describe_format(out.requirements_format, lang)}"
        else:
            scope = "проекта" if out.overridden else "из шаблона"
            header = f"Формат распознавания ({scope}): {describe_format(out.requirements_format, lang)}"
        return ToolResult.ok(f"{header}\n{summarize_matrix(out, lang)}")
