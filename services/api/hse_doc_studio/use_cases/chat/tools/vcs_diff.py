from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.vcs.get_vcs_diff import GetVcsDiffInput, GetVcsDiffUC

_SPEC = ToolSpec(
    name="vcs_diff",
    description=(
        "Показать изменения версии: укажи commit_id, чтобы увидеть, что изменилось в той версии "
        "относительно предыдущей; без commit_id — текущие несохранённые изменения относительно последнего снимка."
    ),
    parameters={
        "type": "object",
        "properties": {
            "commit_id": {"type": "string", "description": "Идентификатор версии (short_id или полный)."},
            "path": {"type": "string", "description": "Ограничить одним файлом/папкой."},
        },
    },
)


class VcsDiffTool:
    def __init__(self, get_diff_uc: GetVcsDiffUC) -> None:
        self._uc = get_diff_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        commit_id = args.get("commit_id")
        path = args.get("path")
        out = await self._uc.execute(
            GetVcsDiffInput(
                project_id=ctx.project_id,
                to_id=commit_id if isinstance(commit_id, str) and commit_id else None,
                path=path if isinstance(path, str) and path else None,
            )
        )
        diff = out.diff
        if not diff.files:
            return ToolResult.ok("no changes" if lang == Lang.en else "изменений нет")
        chunks: list[str] = []
        for file in diff.files:
            header = f"### {file.path} ({file.change})"
            body = ("binary file" if lang == Lang.en else "бинарный файл") if file.binary else file.patch.strip()
            chunks.append(f"{header}\n{body}")
        if diff.truncated:
            note = "\n\n(part of the changes shown)" if lang == Lang.en else "\n\n(показана часть изменений)"
        else:
            note = ""
        return ToolResult.ok("\n\n".join(chunks) + note, truncated=diff.truncated)
