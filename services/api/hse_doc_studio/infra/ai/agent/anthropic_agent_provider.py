from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import anthropic
import structlog

from hse_doc_studio.core.agent.entities import (
    AgentMessage,
    NormalizedTurn,
    TokenUsage,
    ToolCall,
    ToolSpec,
)
from hse_doc_studio.core.agent.protocols import StreamSink
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import StopReason
from hse_doc_studio.infra.ai.agent._support import build_async_http_client
from hse_doc_studio.infra.ai.agent.trace import trace
from hse_doc_studio.infra.docker.siblings import outbound_url

logger = structlog.get_logger()

# Anthropic stop_reason → normalized stop reason.
_STOP_MAP: dict[str, StopReason] = {
    "tool_use": StopReason.tool_calls,
    "end_turn": StopReason.end_turn,
    "stop_sequence": StopReason.end_turn,
    "max_tokens": StopReason.max_tokens,
}


class AnthropicShapedAgentProvider:
    """One normalized agent round-trip over the Anthropic Messages API.

    Built like ``ClaudeClient``. Hides Anthropic's content-block asymmetry from
    the loop: assistant tool requests are ``tool_use`` blocks, tool results are
    ``tool_result`` blocks inside a *user* message, and consecutive tool results
    are merged into a single user message (Anthropic requires all results for one
    assistant turn together). Uses the streaming helper's ``get_final_message``
    so tool-call arguments are parsed by the SDK rather than by hand.
    """

    def __init__(
        self,
        provider: AIProvider,
        *,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self._provider = provider
        self._injected_client = client

    def _build_client(self) -> anthropic.AsyncAnthropic:
        if self._injected_client is not None:
            return self._injected_client
        return anthropic.AsyncAnthropic(
            api_key=self._provider.api_key or "not-needed",
            base_url=outbound_url(self._provider.base_url) or None,
            http_client=build_async_http_client(
                ssl_verify=self._provider.ssl_verify,
                connect_timeout_s=self._provider.connect_timeout_s,
                request_timeout_s=self._provider.request_timeout_s,
            ),
        )

    async def run_turn(
        self,
        *,
        model: str,
        messages: Sequence[AgentMessage],
        tools: Sequence[ToolSpec],
        system: str | None,
        tool_choice_allowed: bool,
        max_output_tokens: int,
        temperature: float,
        sink: StreamSink | None,
        cancel: asyncio.Event,
    ) -> NormalizedTurn:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": self._build_messages(messages),
            "max_tokens": max_output_tokens,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools
            ]
            if tool_choice_allowed:
                kwargs["tool_choice"] = {"type": "auto"}

        trace(
            "anthropic_request",
            model=model,
            base_url=outbound_url(self._provider.base_url) or None,
            tool_choice_allowed=tool_choice_allowed,
            tool_specs=[{"name": t.name, "parameters": t.parameters} for t in tools],
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            system=system,
            messages=kwargs["messages"],
        )

        client = self._build_client()
        try:
            async with client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if cancel.is_set():
                        return NormalizedTurn(
                            text="",
                            tool_calls=(),
                            stop_reason=StopReason.cancelled,
                            usage=TokenUsage(),
                            raw_stop="cancelled",
                        )
                    self._dispatch_event(event, sink)
                final = await stream.get_final_message()
        finally:
            await client.close()

        text = "".join(b.text for b in final.content if b.type == "text")
        calls = tuple(
            ToolCall(
                id=b.id,
                name=b.name,
                arguments=dict(b.input) if isinstance(b.input, dict) else {},
            )
            for b in final.content
            if b.type == "tool_use"
        )
        stop = StopReason.tool_calls if calls else _STOP_MAP.get(final.stop_reason or "", StopReason.end_turn)
        usage = TokenUsage(
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
            cache_read_input_tokens=getattr(final.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(final.usage, "cache_creation_input_tokens", 0) or 0,
        )
        trace(
            "anthropic_turn",
            raw_stop=final.stop_reason or "",
            stop_reason=stop.value,
            tool_calls=[{"id": c.id, "name": c.name, "arguments": c.arguments} for c in calls],
            text=text,
            in_tokens=usage.input_tokens,
            out_tokens=usage.output_tokens,
        )
        return NormalizedTurn(
            text=text, tool_calls=calls, stop_reason=stop, usage=usage, raw_stop=final.stop_reason or ""
        )

    def _dispatch_event(self, event: Any, sink: StreamSink | None) -> None:
        if sink is None:
            return
        etype = event.type
        if etype == "content_block_start":
            block = event.content_block
            if block.type == "tool_use":
                sink.on_tool_call_start(event.index, block.id, block.name)
        elif etype == "content_block_delta":
            delta = event.delta
            if delta.type == "text_delta":
                sink.on_text_delta(delta.text)
            elif delta.type == "input_json_delta":
                sink.on_tool_call_args_delta(event.index, delta.partial_json)

    def _build_messages(self, messages: Sequence[AgentMessage]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        msgs = list(messages)
        i = 0
        while i < len(msgs):
            if msgs[i].role == "tool":
                # Merge a run of consecutive tool results into one user message
                # (Anthropic requires all results for one assistant turn together).
                grouped, i = self._collapse_tool_results(msgs, i)
                out.append(grouped)
                continue
            mapped = self._map_message(msgs[i])
            if mapped is not None:
                out.append(mapped)
            i += 1
        return out

    @staticmethod
    def _collapse_tool_results(msgs: list[AgentMessage], start: int) -> tuple[dict[str, Any], int]:
        blocks: list[dict[str, Any]] = []
        i = start
        while i < len(msgs) and msgs[i].role == "tool":
            tm = msgs[i]
            blocks.append({"type": "tool_result", "tool_use_id": tm.tool_call_id or "", "content": tm.content})
            i += 1
        return {"role": "user", "content": blocks}, i

    @staticmethod
    def _map_message(m: AgentMessage) -> dict[str, Any] | None:
        if m.role == "assistant" and m.tool_calls:
            content: list[dict[str, Any]] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            content.extend(
                {"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments} for tc in m.tool_calls
            )
            return {"role": "assistant", "content": content}
        if m.role in ("user", "assistant"):
            return {"role": m.role, "content": m.content}
        if m.role == "system":
            # Anthropic takes system separately; a stray system message is skipped.
            return None
        return {"role": "user", "content": m.content}
