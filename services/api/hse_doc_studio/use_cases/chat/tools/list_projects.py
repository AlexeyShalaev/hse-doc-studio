from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.projects.list_projects import ListProjectsUC

_SPEC = ToolSpec(
    name="list_projects",
    description="Список зарегистрированных проектов: идентификатор, название и папка на диске.",
    parameters={"type": "object", "properties": {}},
)


class ListProjectsTool:
    def __init__(self, list_projects_uc: ListProjectsUC) -> None:
        self._list = list_projects_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True, requires_project=False
        )

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        out = await self._list.execute()
        if not out.projects:
            return ToolResult.ok("no projects yet" if lang == Lang.en else "проектов пока нет")
        if lang == Lang.en:
            lines = [f"- {p.name} (id {p.id}, folder {p.folder})" for p in out.projects]
            return ToolResult.ok("Projects:\n" + "\n".join(lines))
        lines = [f"- {p.name} (id {p.id}, папка {p.folder})" for p in out.projects]
        return ToolResult.ok("Проекты:\n" + "\n".join(lines))
