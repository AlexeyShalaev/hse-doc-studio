"""Файлы проекта: дерево, запись целиком, перенос и удаление (те же сценарии, что /files и /file-ops)."""

from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.files.delete_file import DeleteFileInput, DeleteFileUC
from hse_doc_studio.use_cases.files.list_file_tree import ListFileTreeInput, ListFileTreeUC
from hse_doc_studio.use_cases.files.move_file import MoveFileInput, MoveFileUC
from hse_doc_studio.use_cases.files.put_file import PutFileInput, PutFileUC, StaleFileError
from hse_doc_studio.use_cases.mcp.tools._base import (
    McpTool,
    int_arg,
    json_result,
    optional_text,
    project_schema,
    text_arg,
)

_TREE_LIMIT = 2000
_PATH = {"type": "string", "description": "Путь относительно корня проекта, напр. vkr/vkr.tex"}


class ListFilesTool(McpTool):
    spec = ToolSpec(
        name="list_files",
        description="Дерево файлов проекта: путь, размер, время изменения, можно ли удалить. prefix сужает список.",
        parameters=project_schema(
            {
                "prefix": {"type": "string", "description": "Только пути с этим началом, напр. vkr/"},
                "limit": {"type": "integer", "default": 500},
            }
        ),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        prefix = optional_text(args, "prefix") or ""
        limit = int_arg(args, "limit", 500, lo=1, hi=_TREE_LIMIT)
        out = await (await self._deps.get(ListFileTreeUC)).execute(ListFileTreeInput(project_id=ctx.project_id))
        items = [i for i in out.items if i.path.startswith(prefix)]
        return json_result(
            {"total": len(items), "items": items[:limit]},
            truncated=len(items) > limit,
        )


class WriteFileTool(McpTool):
    spec = ToolSpec(
        name="write_file",
        description=(
            "Создать или полностью перезаписать текстовый файл проекта (UTF-8). Для точечных правок лучше edit_tex. "
            "if_match (etag из прошлого чтения) защищает от затирания чужих изменений."
        ),
        parameters=project_schema(
            {
                "path": _PATH,
                "content": {"type": "string", "description": "Полный новый текст файла"},
                "if_match": {"type": "string", "description": "Ожидаемый etag текущей версии (необязательно)"},
            },
            ("path", "content"),
        ),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        path = text_arg(args, "path")
        content = args.get("content")
        if not isinstance(content, str):
            return ToolResult.error(localized_error("укажите параметр content", "specify the content parameter"))
        try:
            out = await (await self._deps.get(PutFileUC)).execute(
                PutFileInput(
                    project_id=ctx.project_id,
                    path=path,
                    content=content.encode("utf-8"),
                    if_match=optional_text(args, "if_match"),
                )
            )
        except StaleFileError:
            return ToolResult.error(
                localized_error(
                    f"{path} изменён с прошлого чтения: перечитай файл и повтори",
                    f"{path} changed since it was read: read it again and retry",
                )
            )
        return json_result({"path": path, "etag": out.etag, "bytes": len(content.encode("utf-8"))})


class MoveFileTool(McpTool):
    spec = ToolSpec(
        name="move_file",
        description="Переместить или переименовать файл проекта.",
        parameters=project_schema(
            {"src": {"type": "string", "description": "Откуда"}, "dst": {"type": "string", "description": "Куда"}},
            ("src", "dst"),
        ),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        src, dst = text_arg(args, "src"), text_arg(args, "dst")
        try:
            await (await self._deps.get(MoveFileUC)).execute(MoveFileInput(project_id=ctx.project_id, src=src, dst=dst))
        except FileExistsError:
            return ToolResult.error(localized_error(f"{dst} уже существует", f"{dst} already exists"))
        return ToolResult.ok(localized_error(f"{src} перемещён в {dst}", f"{src} moved to {dst}"))


class DeleteFileTool(McpTool):
    spec = ToolSpec(
        name="delete_file",
        description="Удалить файл проекта. Файлы шаблона удалить нельзя. Вернуть можно из истории (vcs_restore).",
        parameters=project_schema({"path": _PATH}, ("path",)),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        path = text_arg(args, "path")
        await (await self._deps.get(DeleteFileUC)).execute(DeleteFileInput(project_id=ctx.project_id, path=path))
        return ToolResult.ok(localized_error(f"{path} удалён", f"{path} deleted"))
