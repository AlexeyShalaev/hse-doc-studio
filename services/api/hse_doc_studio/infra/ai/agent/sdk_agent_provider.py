from __future__ import annotations

import asyncio
from collections.abc import Sequence

from hse_doc_studio.core.agent.entities import AgentMessage, NormalizedTurn, ToolSpec
from hse_doc_studio.core.agent.protocols import StreamSink
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.infra.ai.agent.anthropic_agent_provider import AnthropicShapedAgentProvider
from hse_doc_studio.infra.ai.agent.openai_agent_provider import OpenAIShapedAgentProvider
from hse_doc_studio.infra.ai.agent.tokenizer import HeuristicTokenizer


class SdkAgentProvider:
    """IAgentProvider implementation that dispatches to the right shape adapter.

    Stateless, like SdkAIModelLister: a fresh adapter is built per call from the
    provider's own settings. ``claude`` → Anthropic-shaped; everything else
    (``openai`` / ``openai_compat`` / ``ollama``) → OpenAI-shaped, with the
    ollama flag set so tool_choice/stream_options are suppressed.
    """

    def __init__(self, tokenizer: HeuristicTokenizer | None = None) -> None:
        self._tokenizer = tokenizer or HeuristicTokenizer()

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
    ) -> NormalizedTurn:
        if provider.type == AIProviderType.claude:
            return await AnthropicShapedAgentProvider(provider).run_turn(
                model=model,
                messages=messages,
                tools=tools,
                system=system,
                tool_choice_allowed=tool_choice_allowed,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                sink=sink,
                cancel=cancel,
            )
        return await OpenAIShapedAgentProvider(
            provider, self._tokenizer, is_ollama=provider.type == AIProviderType.ollama
        ).run_turn(
            model=model,
            messages=messages,
            tools=tools,
            system=system,
            tool_choice_allowed=tool_choice_allowed,
            max_output_tokens=max_output_tokens,
            temperature=temperature,
            sink=sink,
            cancel=cancel,
        )
