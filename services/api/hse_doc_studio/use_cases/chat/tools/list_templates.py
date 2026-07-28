from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import ITemplateRepository

_SPEC = ToolSpec(
    name="list_templates",
    description=(
        "Список доступных шаблонов для создания проекта: pack_id, template_id, название и версия "
        "по умолчанию. Используй перед create_project, чтобы знать допустимые pack_id/template_id/version."
    ),
    parameters={"type": "object", "properties": {}},
)


class ListTemplatesTool:
    def __init__(self, template_repo: ITemplateRepository) -> None:
        self._template_repo = template_repo

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True, requires_project=False
        )

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        packs = self._template_repo.list_packs()
        lines: list[str] = []
        for pack in packs:
            for template in pack.templates:
                name = template.name.get("ru") or template.name.get("en") or template.id
                lines.append(
                    f"- pack_id={pack.id} template_id={template.id} version={template.default_version} — {name}"
                )
        if not lines:
            return ToolResult.ok("no templates found" if lang == Lang.en else "шаблоны не найдены")
        header = "Available templates:\n" if lang == Lang.en else "Доступные шаблоны:\n"
        return ToolResult.ok(header + "\n".join(lines))
