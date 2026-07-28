from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.vcs.get_vcs_status import GetVcsStatusInput, GetVcsStatusUC

_SPEC = ToolSpec(
    name="vcs_status",
    description=(
        "Состояние истории версий проекта (служебный git): текущая ветка, есть ли несохранённые "
        "изменения, когда был последний снимок. Не путать с упаковкой для подачи."
    ),
    parameters={"type": "object", "properties": {}},
)


class VcsStatusTool:
    def __init__(self, get_status_uc: GetVcsStatusUC) -> None:
        self._uc = get_status_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        status = (await self._uc.execute(GetVcsStatusInput(project_id=ctx.project_id))).status
        if not status.available:
            return ToolResult.ok(
                "version history is unavailable (project folder not reachable by the backend)"
                if lang == Lang.en
                else "история версий недоступна (папка проекта недоступна бэкенду)"
            )
        if not status.initialized:
            return ToolResult.ok(
                "version history has not been created for this project yet"
                if lang == Lang.en
                else "история версий ещё не создана для этого проекта"
            )
        changes = status.modified + status.untracked
        if status.dirty:
            dirty = (
                f"unsaved changes present ({changes})"
                if lang == Lang.en
                else f"есть несохранённые изменения ({changes})"
            )
        else:
            dirty = "no unsaved changes" if lang == Lang.en else "нет несохранённых изменений"
        last = status.last_snapshot_at.isoformat() if status.last_snapshot_at else "—"
        branch = status.current_branch or "master"
        if lang == Lang.en:
            return ToolResult.ok(f"Branch: {branch}; {dirty}; last snapshot: {last}")
        return ToolResult.ok(f"Ветка: {branch}; {dirty}; последний снимок: {last}")
