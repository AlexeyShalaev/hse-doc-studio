"""Отказы MCP с кодами (docs/design/mcp.md, раздел 6); текст на языке интерфейса."""

from __future__ import annotations

from enum import StrEnum

from hse_doc_studio.core.i18n import localized_error


class McpErrorCode(StrEnum):
    mcp_disabled = "mcp_disabled"
    tool_disabled = "tool_disabled"
    unknown_tool = "unknown_tool"
    not_found = "not_found"
    forbidden = "forbidden"
    read_only = "read_only"
    rate_limited = "rate_limited"
    quota_exceeded = "quota_exceeded"
    invalid_arguments = "invalid_arguments"
    failed = "failed"


_MESSAGES: dict[McpErrorCode, tuple[str, str]] = {
    McpErrorCode.mcp_disabled: ("MCP выключен в настройках Студии.", "MCP is turned off in the Studio settings."),
    McpErrorCode.tool_disabled: (
        "Этот инструмент выключен в настройках MCP.",
        "This tool is turned off in MCP settings.",
    ),
    McpErrorCode.unknown_tool: ("Нет такого инструмента.", "There is no such tool."),
    McpErrorCode.not_found: ("Не найдено.", "Not found."),
    McpErrorCode.forbidden: ("Недостаточно прав.", "Not enough rights."),
    McpErrorCode.read_only: (
        "Проект открыт только для чтения: запись недоступна.",
        "The project is read-only: writing is not available.",
    ),
    McpErrorCode.rate_limited: ("Слишком много вызовов, повторите позже.", "Too many calls, try again later."),
    McpErrorCode.quota_exceeded: ("Исчерпана квота.", "Quota exceeded."),
    McpErrorCode.invalid_arguments: ("Неверные аргументы.", "Invalid arguments."),
    McpErrorCode.failed: ("Не удалось выполнить.", "The call failed."),
}


def default_message(code: McpErrorCode) -> str:
    ru, en = _MESSAGES[code]
    return localized_error(ru, en)


class McpError(Exception):
    def __init__(self, code: McpErrorCode, message: str | None = None, *, retry_after_s: int | None = None) -> None:
        super().__init__(message or default_message(code))
        self.code = code
        self.retry_after_s = retry_after_s
