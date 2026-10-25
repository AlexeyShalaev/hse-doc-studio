"""Клиенты SDK строятся с нашим HTTP-клиентом без сети.

Регрессия: Anthropic SDK 2.x отвергает клиент `httpx` (ему нужен `httpx2`) уже в
конструкторе, а прочие тесты подменяют SDK-клиент и этого не видят — ошибка
всплыла бы только у пользователя при первом обращении к модели.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.infra.ai.agent.anthropic_agent_provider import AnthropicShapedAgentProvider
from hse_doc_studio.infra.ai.agent.openai_agent_provider import OpenAIShapedAgentProvider
from hse_doc_studio.infra.ai.claude import ClaudeClient
from hse_doc_studio.infra.ai.openai_compat import OpenAICompatClient

pytestmark = pytest.mark.unit


def _provider(kind: AIProviderType, *, ssl_verify: bool) -> AIProvider:
    return AIProvider(
        id=uuid4(),
        name="test",
        type=kind,
        api_key="sk-test",
        base_url="https://example.invalid/v1",
        models=[],
        created_at=datetime.now(tz=timezone.utc),
        ssl_verify=ssl_verify,
    )


@pytest.mark.parametrize("ssl_verify", [True, False])
def test__model_listing_clients__construct(ssl_verify: bool) -> None:
    ClaudeClient("sk-test", "https://example.invalid", ssl_verify=ssl_verify)
    OpenAICompatClient("sk-test", "https://example.invalid/v1", ssl_verify=ssl_verify)


@pytest.mark.parametrize("ssl_verify", [True, False])
def test__agent_provider_clients__construct(ssl_verify: bool) -> None:
    anthropic_client = AnthropicShapedAgentProvider(
        _provider(AIProviderType.claude, ssl_verify=ssl_verify)
    )._build_client()  # noqa: SLF001
    openai_client = OpenAIShapedAgentProvider(_provider(AIProviderType.openai, ssl_verify=ssl_verify))._build_client()  # noqa: SLF001

    asyncio.run(anthropic_client.close())
    asyncio.run(openai_client.close())
