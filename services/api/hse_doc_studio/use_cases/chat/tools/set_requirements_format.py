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
from hse_doc_studio.use_cases.requirements.update_requirements_format import (
    UpdateRequirementsFormatInput,
    UpdateRequirementsFormatUC,
)

_SPEC = ToolSpec(
    name="set_requirements_format",
    description=(
        "Сохранить для проекта формат распознавания требований (переопределяет шаблон пакета): "
        "kind=macro | id (id_pattern + definition_docs) | custom (def_pattern с (?P<id>…) и "
        "ref_pattern с (?P<ids>…)). Сначала подбери паттерн через preview_requirements_format. "
        "Сохранение валидирует regex и сразу возвращает обновлённую матрицу трассировки."
    ),
    parameters=FORMAT_PARAMETERS,
)


class SetRequirementsFormatTool:
    def __init__(
        self,
        update_requirements_format_uc: UpdateRequirementsFormatUC,
        get_requirements_uc: GetRequirementsUC,
    ) -> None:
        self._update = update_requirements_format_uc
        self._get = get_requirements_uc

    def definition(self) -> ToolDefinition:
        # Write kind: persists a project override, so the loop gates it behind the
        # approval gate. Hidden from weak/local models — a mistyped regex from a
        # small model would silently break the scan (mirrors set_project_meta).
        return ToolDefinition(spec=_SPEC, kind=ToolKind.write, handler=self, weak_model_safe=False)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        try:
            fmt = format_from_args(args, lang)
            await self._update.execute(
                UpdateRequirementsFormatInput(project_id=ctx.project_id, requirements_format=fmt)
            )
            out = await self._get.execute(GetRequirementsInput(project_id=ctx.project_id))
        except (ValueError, NotFoundError) as exc:
            # Invalid regex / missing required pattern fields surface here.
            return ToolResult.error(str(exc))
        header = (
            f"Requirements format saved ({describe_format(fmt, lang)}):"
            if lang == Lang.en
            else f"Формат требований сохранён ({describe_format(fmt, lang)}):"
        )
        return ToolResult.ok(f"{header}\n{summarize_matrix(out, lang)}")
