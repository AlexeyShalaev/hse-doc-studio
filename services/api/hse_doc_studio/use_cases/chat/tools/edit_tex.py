from __future__ import annotations

from hse_doc_studio.core.agent.edits import SearchReplaceBlock
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import EditFormat, Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.infra.ai.agent.edit_applier import FuzzySearchReplaceApplier
from hse_doc_studio.use_cases.files.get_file import GetFileInput, GetFileUC
from hse_doc_studio.use_cases.files.put_file import PutFileInput, PutFileUC

_SPEC = ToolSpec(
    name="edit_tex",
    description=(
        "Изменить файл проекта. Сильные модели передают edits — список блоков "
        "{search, replace} по точному тексту файла (поиск с допуском на мелкие "
        "отличия). Слабые/локальные модели передают content — полный новый текст файла."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Путь к файлу относительно корня проекта"},
            "edits": {
                "type": "array",
                "description": "Блоки поиска-замены (для формата search_replace)",
                "items": {
                    "type": "object",
                    "properties": {"search": {"type": "string"}, "replace": {"type": "string"}},
                    "required": ["search", "replace"],
                },
            },
            "content": {"type": "string", "description": "Полный новый текст файла (для формата whole_file)"},
        },
        "required": ["path"],
    },
)


class EditTexTool:
    def __init__(self, get_file_uc: GetFileUC, put_file_uc: PutFileUC, applier: FuzzySearchReplaceApplier) -> None:
        self._get_file = get_file_uc
        self._put_file = put_file_uc
        self._applier = applier

    def definition(self) -> ToolDefinition:
        # weak_model_safe: weak models use the simpler whole_file mode (selected
        # via ctx.edit_format), so the tool is offered to them too.
        return ToolDefinition(spec=_SPEC, kind=ToolKind.write, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        path = str(args.get("path", "")).strip()
        if not path:
            return ToolResult.error("specify the path parameter" if lang == Lang.en else "укажите параметр path")
        if ctx.edit_format == EditFormat.whole_file:
            return await self._whole_file(ctx, path, args, lang)
        return await self._search_replace(ctx, path, args, lang)

    async def _whole_file(self, ctx: AgentToolContext, path: str, args: dict[str, object], lang: Lang) -> ToolResult:
        content = args.get("content")
        if not isinstance(content, str):
            return ToolResult.error(
                "pass content (the full new file text)"
                if lang == Lang.en
                else "передайте content (полный новый текст файла)"
            )
        await self._put_file.execute(
            PutFileInput(project_id=ctx.project_id, path=path, content=content.encode("utf-8"))
        )
        line_count = len(content.splitlines())
        return ToolResult.ok(
            f"file {path} overwritten ({line_count} lines)"
            if lang == Lang.en
            else f"файл {path} перезаписан ({line_count} строк)"
        )

    async def _search_replace(
        self, ctx: AgentToolContext, path: str, args: dict[str, object], lang: Lang
    ) -> ToolResult:
        blocks = _parse_blocks(args.get("edits"))
        if not blocks:
            return ToolResult.error(
                "pass edits — a non-empty list of {search, replace} blocks"
                if lang == Lang.en
                else "передайте edits — непустой список блоков {search, replace}"
            )
        try:
            current = await self._get_file.execute(GetFileInput(project_id=ctx.project_id, path=path))
        except FileNotFoundError:
            return ToolResult.error(f"file not found: {path}" if lang == Lang.en else f"файл не найден: {path}")
        text = current.content.decode("utf-8", errors="replace")
        new_text, errors = self._applier.apply(text, blocks)
        if errors:
            prefix = "edits not applied:\n" if lang == Lang.en else "правки не применены:\n"
            return ToolResult.error(prefix + "\n".join(errors))
        await self._put_file.execute(
            PutFileInput(project_id=ctx.project_id, path=path, content=new_text.encode("utf-8"))
        )
        return ToolResult.ok(
            f"edits applied: {len(blocks)} to file {path}"
            if lang == Lang.en
            else f"применено правок: {len(blocks)} к файлу {path}"
        )


def _parse_blocks(raw: object) -> list[SearchReplaceBlock]:
    if not isinstance(raw, list):
        return []
    return [
        SearchReplaceBlock(search=item["search"], replace=item["replace"])
        for item in raw
        if isinstance(item, dict) and isinstance(item.get("search"), str) and isinstance(item.get("replace"), str)
    ]
