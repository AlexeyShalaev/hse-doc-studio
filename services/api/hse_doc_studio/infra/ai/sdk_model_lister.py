from __future__ import annotations

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.infra.ai.claude import ClaudeClient
from hse_doc_studio.infra.ai.openai_compat import OpenAICompatClient
from hse_doc_studio.infra.docker.siblings import outbound_url


class SdkAIModelLister:
    """IAIModelLister implementation backed by the official openai/anthropic SDKs.

    Stateless: a fresh SDK client is built per call from the provider's own
    api_key/base_url/ssl/timeout settings (these differ per provider, so there
    is no shared long-lived client to inject).
    """

    async def list_models(self, provider: AIProvider) -> list[str]:
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
