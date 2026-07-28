from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.vcs.create_vcs_snapshot import (
    CreateVcsSnapshotInput,
    CreateVcsSnapshotUC,
)

_SPEC = ToolSpec(
    name="vcs_save_snapshot",
    description=(
        "Сохранить именованный снимок текущего состояния проекта в историю версий (служебный git). "
        "Используй перед рискованной правкой или чтобы зафиксировать веху. Это только добавляет версию."
    ),
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Короткое описание снимка, напр. 'до переписывания главы 3'."},
        },
        "required": ["message"],
    },
)


class VcsSaveSnapshotTool:
    def __init__(self, snapshot_uc: CreateVcsSnapshotUC) -> None:
        self._uc = snapshot_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.write, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        message = args.get("message")
        if not isinstance(message, str) or not message.strip():
            return ToolResult.error(
                "provide a non-empty message for the snapshot"
                if lang == Lang.en
                else "передайте непустое message для снимка"
            )
        out = await self._uc.execute(CreateVcsSnapshotInput(project_id=ctx.project_id, message=message.strip()))
        if out.commit is None:
            return ToolResult.ok("no changes to snapshot" if lang == Lang.en else "нет изменений для снимка")
        if lang == Lang.en:
            return ToolResult.ok(f"snapshot saved: {out.commit.short_id} «{out.commit.message}»")
        return ToolResult.ok(f"снимок сохранён: {out.commit.short_id} «{out.commit.message}»")
