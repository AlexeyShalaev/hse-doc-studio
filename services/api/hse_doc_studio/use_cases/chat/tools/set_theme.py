from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.settings.update_settings import UpdateSettingsInput, UpdateSettingsUC

_ALLOWED = ("system", "dark", "light")

_SPEC = ToolSpec(
    name="set_theme",
    description="Сменить тему оформления приложения (system — следовать за ОС, dark или light).",
    parameters={
        "type": "object",
        "properties": {"theme": {"type": "string", "enum": list(_ALLOWED)}},
        "required": ["theme"],
    },
)


class SetThemeTool:
    def __init__(self, update_settings_uc: UpdateSettingsUC) -> None:
        self._update_settings = update_settings_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            spec=_SPEC, kind=ToolKind.write, handler=self, weak_model_safe=True, requires_project=False
        )

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        theme = str(args.get("theme", "")).strip().lower()
        if theme not in _ALLOWED:
            allowed = ", ".join(_ALLOWED)
            return ToolResult.error(
                f"theme must be one of: {allowed}" if lang == Lang.en else f"тема должна быть одной из: {allowed}"
            )
        await self._update_settings.execute(UpdateSettingsInput(patch={"theme": theme}))
        return ToolResult.ok(
            f"app theme switched to «{theme}»" if lang == Lang.en else f"тема приложения переключена на «{theme}»"
        )
