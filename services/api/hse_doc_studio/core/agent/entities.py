from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from hse_doc_studio.core.enums import AgentEventType, EditFormat, StopReason

# Provider-neutral types for one agent model round-trip. Both the OpenAI-shaped
# and Anthropic-shaped adapters map their native request/response onto these, so
# the agent loop never sees provider differences (mirrors how IAIModelLister
# hides the SDK split behind one protocol).


@dataclass(frozen=True)
class ToolSpec:
    # A tool advertised to the model. `parameters` is a JSON Schema object both
    # the OpenAI `function.parameters` and Anthropic `input_schema` fields accept.
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    # A tool invocation the model requested. `arguments` is already parsed (the
    # adapter owns JSON parsing + repair); `raw_arguments` keeps the original
    # string for error messages when parsing failed.
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass(frozen=True)
class ToolResult:
    # The outcome of running a tool, fed back to the model as a tool message.
    # `text` is human-readable (no opaque identifiers); `truncated` flags that a
    # token cap was applied so the model knows it can paginate.
    text: str
    is_error: bool = False
    truncated: bool = False

    @classmethod
    def ok(cls, text: str, *, truncated: bool = False) -> ToolResult:
        return cls(text=text, is_error=False, truncated=truncated)

    @classmethod
    def error(cls, text: str) -> ToolResult:
        return cls(text=text, is_error=True)


@dataclass(frozen=True)
class TokenUsage:
    # Token accounting for a turn. Anthropic and OpenAI (with include_usage)
    # report these directly; for endpoints that don't, the adapter estimates.
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class AgentMessage:
    # The provider-neutral message the loop hands to IAgentProvider.run_turn.
    # role is "system" | "user" | "assistant" | "tool". An assistant turn that
    # requested tools carries `tool_calls`; a tool result carries `tool_call_id`
    # (+ human-readable `name`). The persisted ChatMessage is projected onto this.
    role: str
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class NormalizedTurn:
    # The normalized result of one model round-trip, identical across providers.
    text: str
    tool_calls: tuple[ToolCall, ...]
    stop_reason: StopReason
    usage: TokenUsage
    raw_stop: str = ""  # native finish_reason/stop_reason, kept for logging


@dataclass(frozen=True)
class AgentEvent:
    # One streamed event during a run. `type` selects the SSE event name; `data`
    # is the JSON payload. The run bus carries these; the API serializes them.
    type: AgentEventType
    data: dict[str, Any]


@dataclass(frozen=True)
class AgentToolContext:
    # Ambient context every tool handler receives. `edit_format` is chosen per
    # model (strong → search_replace, weak/local → whole_file) and read by
    # edit_tex; project tools resolve the project from `project_id`. Outside a
    # project (unified agent, system scope) this is a dummy id and only tools
    # with requires_project=False run — the loop gates the rest by `has_project`.
    project_id: UUID
    model: str
    edit_format: EditFormat
    extra: dict[str, Any] = field(default_factory=dict)
