from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.chat.tools._requirements_format import (
    FORMAT_PARAMETERS,
    describe_format,
    format_from_args,
    summarize_matrix,
)
from hse_doc_studio.use_cases.requirements.get_requirements import (
    GetRequirementsInput,
    GetRequirementsUC,
)

_SPEC = ToolSpec(
    name="preview_requirements_format",
    description=(
        "Пробный прогон формата распознавания требований БЕЗ сохранения: сканирует .tex "
        "проекта по переданному формату (kind + regex/паттерны) и возвращает получившуюся "
        "матрицу — сколько требований найдено, покрыто, без ссылок, без определения. "
        "Используй, чтобы подобрать и проверить id_pattern/regex (сначала посмотри реальные "
        "ID через grep_project/read_tex), прежде чем применять set_requirements_format."
    ),
    parameters=FORMAT_PARAMETERS,
)


class PreviewRequirementsFormatTool:
    def __init__(self, get_requirements_uc: GetRequirementsUC) -> None:
        self._get_requirements = get_requirements_uc

    def definition(self) -> ToolDefinition:
        # Read kind: a dry run that persists nothing, so it auto-runs and is safe
        # even for weak/local models to iterate a regex against the real sources.
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        try:
            fmt = format_from_args(args, lang)
            out = await self._get_requirements.execute(
                GetRequirementsInput(project_id=ctx.project_id, format_override=fmt)
            )
        except (ValueError, NotFoundError) as exc:
            return ToolResult.error(str(exc))
        header = (
            f"Dry run of format ({describe_format(fmt, lang)}):"
            if lang == Lang.en
            else f"Пробный прогон формата ({describe_format(fmt, lang)}):"
        )
        return ToolResult.ok(f"{header}\n{summarize_matrix(out, lang)}")
