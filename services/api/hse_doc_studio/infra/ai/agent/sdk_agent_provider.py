from __future__ import annotations

import asyncio
from collections.abc import Sequence
from uuid import UUID

import httpx2
import openai

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.agent.entities import AgentMessage, NormalizedTurn, ToolSpec
from hse_doc_studio.core.agent.protocols import StreamSink
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.jobs.relay import AiEndpointFlavor
from hse_doc_studio.infra.ai.agent.anthropic_agent_provider import AnthropicShapedAgentProvider
from hse_doc_studio.infra.ai.agent.openai_agent_provider import OpenAIShapedAgentProvider
from hse_doc_studio.infra.ai.agent.tokenizer import HeuristicTokenizer
from hse_doc_studio.infra.ai.relay_transport import RELAY_BASE_URL, RunnerRelayTransport
from hse_doc_studio.use_cases.ai_relay.client import AiRelayClient


class SdkAgentProvider:
    """IAgentProvider implementation that dispatches to the right shape adapter.

    Stateless, like SdkAIModelLister: a fresh adapter is built per call from the
    provider's own settings. ``claude`` → Anthropic-shaped; everything else
    (``openai`` / ``openai_compat`` / ``ollama``) → OpenAI-shaped, with the
    ollama flag set so tool_choice/stream_options are suppressed.
    """

    def __init__(self, tokenizer: HeuristicTokenizer | None = None, relay: AiRelayClient | None = None) -> None:
        self._tokenizer = tokenizer or HeuristicTokenizer()
        self._relay = relay

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
        project_id: UUID | None = None,
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
        if provider.type is AIProviderType.runner:
            adapter = await self._runner_adapter(provider, project_id)
        else:
            adapter = OpenAIShapedAgentProvider(
                provider, self._tokenizer, is_ollama=provider.type == AIProviderType.ollama
            )
        return await adapter.run_turn(
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

    async def _runner_adapter(self, provider: AIProvider, project_id: UUID | None) -> OpenAIShapedAgentProvider:
        """OpenAI-путь через ретрансляцию: поправки Ollama по виду адреса, объявленному раннером, без повторов SDK.

        Проект чата уходит в задачу очереди, чтобы админка видела, к какому проекту относится ретрансляция.
        """
        if self._relay is None:
            raise RuntimeError("runner providers need the relay client (server mode)")
        actor = require_actor()
        endpoint = provider.runner_endpoint or ""
        runner = await self._relay.check(actor, provider.runner_id or "", endpoint)
        declared = runner.ai_endpoint(endpoint)
        client = openai.AsyncOpenAI(
            api_key="not-needed",
            base_url=RELAY_BASE_URL,
            max_retries=0,
            http_client=httpx2.AsyncClient(
                transport=RunnerRelayTransport(self._relay, actor, provider, project_id),
                timeout=httpx2.Timeout(provider.request_timeout_s, connect=provider.connect_timeout_s),
            ),
        )
        return OpenAIShapedAgentProvider(
            provider,
            self._tokenizer,
            is_ollama=declared is not None and declared.flavor is AiEndpointFlavor.ollama,
            client=client,
        )
