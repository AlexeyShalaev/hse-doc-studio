from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Protocol

from hse_doc_studio.core.agent.entities import (
    AgentMessage,
    AgentToolContext,
    NormalizedTurn,
    ToolResult,
    ToolSpec,
)
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import ToolKind


class StreamSink(Protocol):
    # Push surface the loop hands to a provider so UI deltas stream as they
    # arrive. All non-async (cheap); the provider calls them between chunks.
    def on_text_delta(self, text: str) -> None: ...
    def on_tool_call_start(self, index: int, call_id: str, name: str) -> None: ...
    def on_tool_call_args_delta(self, index: int, args_fragment: str) -> None: ...


class IAgentProvider(Protocol):
    # One model round-trip, normalized. Defined in core so the loop/use cases
    # depend on it without importing infra; the SDK-backed dispatcher lives in
    # infra/ai/agent. `tool_choice_allowed` is False for Ollama (its OpenAI-compat
    # endpoint rejects tool_choice). `cancel` is checked between streamed chunks.
    async def run_turn(
        self,
        *,
        provider: AIProvider,
        model: str,
        messages: Sequence[AgentMessage],
        tools: Sequence[ToolSpec],
        system: str | None,
        tool_choice_allowed: bool,
        max_output_tokens: int,
        temperature: float,
        sink: StreamSink | None,
        cancel: asyncio.Event,
    ) -> NormalizedTurn: ...


class IToolHandler(Protocol):
    # Runs one tool. Implementations live in use_cases/chat/tools and wrap an
    # existing use case; they never touch infra directly.
    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult: ...


class IApprovalGate(Protocol):
    # Decides whether a tool of the given kind needs explicit user approval
    # before running. read → auto; write/exec → gated unless config opts in.
    def requires_approval(self, kind: ToolKind) -> bool: ...
