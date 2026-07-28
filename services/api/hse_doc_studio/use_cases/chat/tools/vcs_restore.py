from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind, VcsRestoreMode
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.vcs.restore_vcs import RestoreVcsInput, RestoreVcsUC

_SPEC = ToolSpec(
    name="vcs_restore",
    description=(
        "Безопасно откатить проект к прошлой версии по commit_id. Текущее состояние сначала сохраняется "
        "отдельным снимком, затем файлы возвращаются к выбранной версии новым снимком — ничего не теряется, "
        "откат можно отменить. Деструктивного режима у инструмента нет."
    ),
    parameters={
        "type": "object",
        "properties": {
            "commit_id": {"type": "string", "description": "Идентификатор версии, к которой вернуться."},
        },
        "required": ["commit_id"],
    },
)


class VcsRestoreTool:
    def __init__(self, restore_uc: RestoreVcsUC) -> None:
        self._uc = restore_uc

    def definition(self) -> ToolDefinition:
        # exec: gated by the approval gate. Always SAFE snapshot-restore — there is
        # no `mode` parameter, so the model can never trigger a destructive reset.
        return ToolDefinition(spec=_SPEC, kind=ToolKind.exec_, handler=self, weak_model_safe=False)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        commit_id = args.get("commit_id")
        if not isinstance(commit_id, str) or not commit_id.strip():
            return ToolResult.error(
                "provide the commit_id of the version to restore"
                if lang == Lang.en
                else "передайте commit_id версии для отката"
            )
        out = await self._uc.execute(
            RestoreVcsInput(
                project_id=ctx.project_id,
                commit_id=commit_id.strip(),
                mode=VcsRestoreMode.snapshot,
            )
        )
        result = out.result
        new = result.new_snapshot_id[:7] if result.new_snapshot_id else "—"
        restored_from = result.restored_from[:7]
        if lang == Lang.en:
            return ToolResult.ok(
                f"restored to version {restored_from}; "
                f"recovery snapshot {new} created ({result.files_changed} file(s) changed)"
            )
        return ToolResult.ok(
            f"откат к версии {restored_from} выполнен; "
            f"создан восстановительный снимок {new} ({result.files_changed} файл. изменено)"
        )
