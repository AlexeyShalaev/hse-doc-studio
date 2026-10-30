"""Права на вызов инструмента агента: те же действия и области, что у маршрутов проекта.

Агент работает от имени актора запроса и не должен уметь больше него. Гард маршрутов инструменты не видит,
поэтому каждый вызов проверяется здесь через `IProjectAccessChecker`. Инструмент без записи в таблице получает
только AGENT_USE; тест сверяет таблицу с реестром, так что новый инструмент приходится описать явно.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker


@dataclass(frozen=True, slots=True)
class ToolAccess:
    action: Action
    # Аргумент вызова с путём файла: область проверки для действий над файлами.
    path_arg: str | None = None


TOOL_ACCESS: Mapping[str, ToolAccess] = {
    "read_tex": ToolAccess(Action.FILES_READ, "path"),
    "read_pdf": ToolAccess(Action.FILES_READ, "path"),
    "edit_tex": ToolAccess(Action.FILES_WRITE, "path"),
    "grep_project": ToolAccess(Action.SOURCES_READ),
    "vcs_status": ToolAccess(Action.SOURCES_READ),
    "vcs_diff": ToolAccess(Action.SOURCES_READ),
    "vcs_list_history": ToolAccess(Action.SOURCES_READ),
    "list_documents": ToolAccess(Action.PROJECT_VIEW),
    "trace_requirements": ToolAccess(Action.PROJECT_VIEW),
    "preview_requirements_format": ToolAccess(Action.PROJECT_VIEW),
    "list_check_findings": ToolAccess(Action.OUTPUT_READ),
    "compile_document": ToolAccess(Action.BUILD_RUN),
    "set_project_meta": ToolAccess(Action.PROJECT_SETTINGS),
    "set_language": ToolAccess(Action.PROJECT_SETTINGS),
    "set_requirements_format": ToolAccess(Action.PROJECT_SETTINGS),
    # Автора пакета проверяет сам сценарий сдачи: слаг в аргументах инструмента не приходит.
    "package_project": ToolAccess(Action.SUBMISSION_CREATE),
    "vcs_save_snapshot": ToolAccess(Action.HISTORY_WRITE),
    "vcs_restore": ToolAccess(Action.HISTORY_REWRITE),
}


_DEFAULT = ToolAccess(Action.AGENT_USE)


async def require_tool_access(
    access: IProjectAccessChecker, project_id: UUID, tool_name: str, args: Mapping[str, object]
) -> None:
    """Бросает ProjectForbiddenError или NotFoundError, если актору инструмент не положен."""
    rule = TOOL_ACCESS.get(tool_name, _DEFAULT)
    path = str(args.get(rule.path_arg, "")).strip() if rule.path_arg is not None else None
    await access.require(project_id, rule.action, path)
