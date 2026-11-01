"""Список моделей провайдера через SDK; провайдер «через мой раннер» идёт ретрансляцией без сети сервера."""

from __future__ import annotations

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.infra.ai.claude import ClaudeClient
from hse_doc_studio.infra.ai.openai_compat import OpenAICompatClient
from hse_doc_studio.infra.ai.relay_transport import RELAY_BASE_URL, RunnerRelayTransport
from hse_doc_studio.infra.docker.siblings import outbound_url
from hse_doc_studio.use_cases.ai_relay.client import AiRelayClient


class SdkAIModelLister:
    """IAIModelLister implementation backed by the official openai/anthropic SDKs.

    Stateless: a fresh SDK client is built per call from the provider's own
    api_key/base_url/ssl/timeout settings (these differ per provider, so there
    is no shared long-lived client to inject). `relay` is set on a server:
    a `runner` provider lists models through the owner's runner.
    """

    def __init__(self, relay: AiRelayClient | None = None) -> None:
        self._relay = relay

    async def list_models(self, provider: AIProvider) -> list[str]:
        if provider.type is AIProviderType.runner:
            return await self._list_via_runner(provider)
        # Пользователь пишет адрес так, как видит его у СЕБЯ; из контейнера
        # `localhost` — это мы сами, поэтому наружу идём через хостовый шлюз.
        base_url = outbound_url(provider.base_url) or None
        if provider.type == AIProviderType.claude:
            client: ClaudeClient | OpenAICompatClient = ClaudeClient(
                api_key=provider.api_key,
                base_url=base_url,
                ssl_verify=provider.ssl_verify,
                connect_timeout_s=provider.connect_timeout_s,
                request_timeout_s=provider.request_timeout_s,
            )
        else:
            client = OpenAICompatClient(
                api_key=provider.api_key,
                base_url=base_url,
                ssl_verify=provider.ssl_verify,
                connect_timeout_s=provider.connect_timeout_s,
                request_timeout_s=provider.request_timeout_s,
            )
        return await client.list_models()

    async def _list_via_runner(self, provider: AIProvider) -> list[str]:
        if self._relay is None:
            raise RuntimeError("runner providers need the relay client (server mode)")
        actor = require_actor()
        assert provider.runner_id is not None  # noqa: S101 — вид runner без раннера не сохраняется
        await self._relay.check(actor, provider.runner_id, provider.runner_endpoint or "")
        client = OpenAICompatClient(
            api_key="not-needed",
            base_url=RELAY_BASE_URL,
            connect_timeout_s=provider.connect_timeout_s,
            request_timeout_s=provider.request_timeout_s,
            transport=RunnerRelayTransport(self._relay, actor, provider, None),
            # Повтор съел бы лимит одновременных ретрансляций человека.
            max_retries=0,
        )
        return await client.list_models()
