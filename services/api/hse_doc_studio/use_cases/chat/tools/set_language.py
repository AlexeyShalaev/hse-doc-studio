from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.projects.update_project import UpdateProjectInput, UpdateProjectUC

_SPEC = ToolSpec(
    name="set_language",
    description="Сменить язык работы проекта (ru или en). Документы ЕСПД для кафедры всё равно сдаются на русском.",
    parameters={
        "type": "object",
        "properties": {"language": {"type": "string", "enum": ["ru", "en"]}},
        "required": ["language"],
    },
)


class SetLanguageTool:
    def __init__(self, update_project_uc: UpdateProjectUC) -> None:
        self._update_project = update_project_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.write, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        ui_lang = current_interface_language()
        raw = str(args.get("language", "")).strip().lower()
        try:
            lang = Lang(raw)
        except ValueError:
            return ToolResult.error("language must be ru or en" if ui_lang == Lang.en else "язык должен быть ru или en")
        await self._update_project.execute(UpdateProjectInput(project_id=ctx.project_id, lang=lang))
        return ToolResult.ok(
            f"the project's working language was switched to «{lang}»"
            if ui_lang == Lang.en
            else f"язык работы проекта переключён на «{lang}»"
        )
