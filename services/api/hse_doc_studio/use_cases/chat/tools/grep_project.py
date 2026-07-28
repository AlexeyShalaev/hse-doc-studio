from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.agent.tools import ToolDefinition
from hse_doc_studio.core.enums import Lang, ToolKind
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.repositories import IFileRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectInput, GetProjectUC

_DEFAULT_MAX_RESULTS = 100

_SPEC = ToolSpec(
    name="grep_project",
    description=(
        "Поиск по регулярному выражению в файлах проекта. Возвращает совпадения в виде "
        "path:line: текст. По умолчанию ищет в *.tex."
    ),
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Регулярное выражение (Python re)"},
            "glob": {"type": "string", "description": "Маска файлов", "default": "*.tex"},
            "max_results": {"type": "integer", "description": "Максимум совпадений", "default": _DEFAULT_MAX_RESULTS},
        },
        "required": ["pattern"],
    },
)


class GrepProjectTool:
    def __init__(self, file_repo: IFileRepository, get_project_uc: GetProjectUC) -> None:
        self._file_repo = file_repo
        self._get_project = get_project_uc

    def definition(self) -> ToolDefinition:
        return ToolDefinition(spec=_SPEC, kind=ToolKind.read, handler=self, weak_model_safe=True)

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        lang = current_interface_language()
        pattern = str(args.get("pattern", "")).strip()
        if not pattern:
            return ToolResult.error("specify the pattern parameter" if lang == Lang.en else "укажите параметр pattern")
        try:
            regex = re.compile(pattern, re.MULTILINE)
        except re.error as exc:
            return ToolResult.error(
                f"invalid regular expression: {exc}" if lang == Lang.en else f"некорректное регулярное выражение: {exc}"
            )
        glob = str(args.get("glob") or "*.tex")
        max_results = max(1, _as_int(args.get("max_results"), _DEFAULT_MAX_RESULTS))

        result = await self._get_project.execute(GetProjectInput(project_id=ctx.project_id))
        folder = result.project.folder
        paths = sorted(p for p in self._file_repo.list_files(folder) if fnmatch.fnmatch(p.lower(), glob.lower()))
        hits = self._search(folder, paths, regex, max_results)

        if not hits:
            return ToolResult.ok(
                f"no matches found (pattern={pattern!r}, glob={glob})"
                if lang == Lang.en
                else f"совпадений не найдено (pattern={pattern!r}, glob={glob})"
            )
        capped = (" (showing first)" if lang == Lang.en else " (показаны первые)") if len(hits) >= max_results else ""
        header = (
            f"Found {len(hits)} matches{capped}:\n" if lang == Lang.en else f"Найдено {len(hits)} совпадений{capped}:\n"
        )
        return ToolResult.ok(header + "\n".join(hits), truncated=bool(capped))

    def _search(self, folder: Path, paths: list[str], regex: re.Pattern[str], max_results: int) -> list[str]:
        hits: list[str] = []
        for path in paths:
            try:
                content = self._file_repo.read(folder, path).decode("utf-8", errors="replace")
            except (FileNotFoundError, PermissionError):
                continue
            for lineno, line in enumerate(content.splitlines(), start=1):
                if regex.search(line):
                    hits.append(f"{path}:{lineno}: {line.strip()}")
                    if len(hits) >= max_results:
                        return hits
        return hits


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
