from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.use_cases.files.get_file import GetFileInput, GetFileUC

_DEFAULT_LIMIT = 400

_SPEC = ToolSpec(
    name="read_tex",
    description=(
        "Прочитать файл проекта (.tex и др.) с нумерацией строк. Большие файлы читай "
        "постранично через offset/limit (в строках)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Путь относительно корня проекта, напр. vkr/vkr.tex"},
            "offset": {"type": "integer", "description": "С какой строки начать (0-based)", "default": 0},
            "limit": {"type": "integer", "description": "Сколько строк вернуть", "default": _DEFAULT_LIMIT},
        },
        "required": ["path"],
    },
)


class ReadTexTool:
    def __init__(self, get_file_uc: GetFileUC) -> None:
        self._get_file = get_file_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        path = str(args.get("path", "")).strip()
        if not path:
            return ToolResult.error("specify the path parameter" if lang == Lang.en else "укажите параметр path")
        try:
            out = await self._get_file.execute(GetFileInput(project_id=ctx.project_id, path=path))
        except FileNotFoundError:
            return ToolResult.error(f"file not found: {path}" if lang == Lang.en else f"файл не найден: {path}")
        except Exception as exc:  # noqa: BLE001 — surface a clean message to the model, never crash the loop
            return ToolResult.error(
                f"could not read {path}: {type(exc).__name__}"
                if lang == Lang.en
                else f"не удалось прочитать {path}: {type(exc).__name__}"
            )

        lines = out.content.decode("utf-8", errors="replace").splitlines()
        offset = max(0, _as_int(args.get("offset"), 0))
        limit = max(1, _as_int(args.get("limit"), _DEFAULT_LIMIT))
        window = lines[offset : offset + limit]
        body = "\n".join(f"{offset + i + 1}: {line}" for i, line in enumerate(window))
        end = offset + len(window)
        footer = ""
        if end < len(lines):
            remaining = len(lines) - end
            footer = (
                f"\n[... {remaining} more lines; call again with offset={end}]"
                if lang == Lang.en
                else f"\n[... ещё {remaining} строк; вызови снова с offset={end}]"
            )
        header = (
            f"{path} (lines {offset + 1}–{end} of {len(lines)}):"
            if lang == Lang.en
            else f"{path} (строки {offset + 1}–{end} из {len(lines)}):"
        )
        return ToolResult.ok(f"{header}\n{body}{footer}", truncated=bool(footer))


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default
