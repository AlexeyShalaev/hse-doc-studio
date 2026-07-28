from __future__ import annotations

import json
from collections.abc import Sequence

from hse_doc_studio.core.agent.entities import AgentMessage, ToolSpec

# A model turn reports real token usage on most providers (Anthropic always;
# OpenAI with stream_options include_usage). This heuristic (~4 chars/token) is
# only a pre-send budget guard and a fallback for endpoints that omit usage.
_CHARS_PER_TOKEN = 4


class HeuristicTokenizer:
    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(1, len(text) // _CHARS_PER_TOKEN)

    def count_messages(
        self,
        messages: Sequence[AgentMessage],
        *,
        system: str | None = None,
        tools: Sequence[ToolSpec] = (),
    ) -> int:
        total = self.count(system or "")
        for message in messages:
            total += self.count(message.content)
            for call in message.tool_calls:
                total += self.count(call.name) + self.count(json.dumps(call.arguments, ensure_ascii=False))
        for tool in tools:
            total += (
                self.count(tool.name)
                + self.count(tool.description)
                + self.count(json.dumps(tool.parameters, ensure_ascii=False))
            )
        return total
