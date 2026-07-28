from __future__ import annotations

from hse_doc_studio.core.agent.entities import TokenUsage, ToolResult
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language

_CHARS_PER_TOKEN = 4


class TokenBudget:
    """Running token total for one turn, checked before each model round-trip."""

    def __init__(self, total: int) -> None:
        self._total = total
        self._spent = 0

    def add(self, usage: TokenUsage) -> None:
        self._spent += usage.total_tokens

    @property
    def spent(self) -> int:
        return self._spent

    def exhausted(self) -> bool:
        return self._spent >= self._total


def truncate_tool_result(result: ToolResult, max_tokens: int) -> ToolResult:
    """Cap a tool result to a token budget so a huge output can't blow context.

    Approximate (chars/token); appends a marker so the model knows it was cut and
    can paginate via the tool's own offset/limit parameters.
    """
    max_chars = max(0, max_tokens) * _CHARS_PER_TOKEN
    if max_chars == 0 or len(result.text) <= max_chars:
        return result
    head = result.text[:max_chars]
    if current_interface_language() is Lang.en:
        marker = f"\n[... truncated: showing ~{max_chars} of {len(result.text)} characters]"
    else:
        marker = f"\n[... обрезано: показано ~{max_chars} из {len(result.text)} символов]"
    return ToolResult(text=head + marker, is_error=result.is_error, truncated=True)
