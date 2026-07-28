from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.settings.update_settings import UpdateSettingsInput, UpdateSettingsUC

_ALLOWED = ("xelatex", "pdflatex", "lualatex")

_SPEC = ToolSpec(
    name="set_engine",
    description="Сменить движок сборки LaTeX по умолчанию (xelatex, pdflatex или lualatex).",
    parameters={
        "type": "object",
        "properties": {"engine": {"type": "string", "enum": list(_ALLOWED)}},
        "required": ["engine"],
    },
)


class SetEngineTool:
    def __init__(self, update_settings_uc: UpdateSettingsUC) -> None:
        self._update_settings = update_settings_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            spec=_SPEC, kind=ToolKind.write, handler=self, weak_model_safe=True, requires_project=False
        )

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        engine = str(args.get("engine", "")).strip().lower()
        if engine not in _ALLOWED:
            allowed = ", ".join(_ALLOWED)
            return ToolResult.error(
                f"engine must be one of: {allowed}" if lang == Lang.en else f"движок должен быть одним из: {allowed}"
            )
        await self._update_settings.execute(UpdateSettingsInput(patch={"default_engine": engine}))
        return ToolResult.ok(
            f"default build engine switched to «{engine}»"
            if lang == Lang.en
            else f"движок сборки по умолчанию переключён на «{engine}»"
        )
