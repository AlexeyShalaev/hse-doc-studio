from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.use_cases.office_editor.ai_settings import build_ai_plugin_settings


def _provider(
    type_: AIProviderType,
    *,
    name: str = "Provider",
    api_key: str = "sk-key",
    base_url: str = "",
    models: list[str] | None = None,
) -> AIProvider:
    return AIProvider(
        id=uuid4(),
        name=name,
        type=type_,
        api_key=api_key,
        base_url=base_url,
        models=models or [],
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.unit
def test__build__claude_maps_to_anthropic_with_default_url() -> None:
    provider = _provider(AIProviderType.claude, name="Мой Claude", models=["claude-sonnet-4-5"])

    out = build_ai_plugin_settings([provider], {})

    # Имя обязано быть "Anthropic": плагин выбирает протокол по имени класса.
    entry = out["providers"]["Anthropic"]
    assert entry["url"] == "https://api.anthropic.com"
    assert entry["key"] == "sk-key"
    assert entry["models"] == [
        {"id": "claude-sonnet-4-5", "name": "claude-sonnet-4-5", "endpoints": [1], "options": {}}
    ]
    assert out["models"] == [
        {"name": "Anthropic [claude-sonnet-4-5]", "id": "claude-sonnet-4-5", "provider": "Anthropic", "capabilities": 1}
    ]
    # Текстовые actions получают модель (без этого DS считает настройки пустыми).
    for action in ("Chat", "Summarization", "Translation", "TextAnalyze"):
        assert out["actions"][action] == {"model": "claude-sonnet-4-5"}
    for action in ("ImageGeneration", "OCR", "Vision"):
        assert out["actions"][action] == {"model": ""}
    assert out["proxy"] == "/ai-proxy"


@pytest.mark.unit
def test__build__second_claude_is_skipped() -> None:
    first = _provider(AIProviderType.claude, name="Claude 1", models=["m1"])
    second = _provider(AIProviderType.claude, name="Claude 2", models=["m2"])

    out = build_ai_plugin_settings([first, second], {})

    # Класс "Anthropic" один — второго claude выразить нечем (базовый класс
    # сломал бы протокол против api.anthropic.com).
    assert list(out["providers"].keys()) == ["Anthropic"]
    assert [m["id"] for m in out["models"]] == ["m1"]


@pytest.mark.unit
def test__build__openai_and_compat_and_ollama_mapping() -> None:
    openai = _provider(AIProviderType.openai, name="OpenAI осн.", models=["gpt-4o"])
    compat = _provider(
        AIProviderType.openai_compat,
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        models=["meta-llama/llama-3-70b"],
    )
    ollama = _provider(
        AIProviderType.ollama,
        name="Локальные модели",
        api_key="",
        base_url="http://127.0.0.1:11434/v1",
        models=["qwen2.5:7b"],
    )

    out = build_ai_plugin_settings([openai, compat, ollama], {})

    assert out["providers"]["OpenAI"]["url"] == "https://api.openai.com"
    # openai_compat живёт под своим именем (базовый OpenAI-совместимый класс).
    assert out["providers"]["OpenRouter"]["url"] == "https://openrouter.ai/api/v1"
    # localhost переписывается: прокси-запросы уходят ИЗ контейнера DS.
    assert out["providers"]["Ollama"]["url"] == "http://host.docker.internal:11434/v1"
    assert {m["provider"] for m in out["models"]} == {"OpenAI", "OpenRouter", "Ollama"}


@pytest.mark.unit
def test__build__default_model_from_app_settings_wins() -> None:
    first = _provider(AIProviderType.openai, models=["gpt-4o", "gpt-4o-mini"])
    second = _provider(AIProviderType.claude, models=["claude-sonnet-4-5", "claude-haiku-4-5"])

    out = build_ai_plugin_settings(
        [first, second],
        {"default_ai_provider_id": str(second.id), "default_ai_model": "claude-haiku-4-5"},
    )

    assert out["actions"]["Chat"] == {"model": "claude-haiku-4-5"}


@pytest.mark.unit
def test__build__no_models_yields_empty_settings() -> None:
    empty_provider = _provider(AIProviderType.openai, models=[])

    out = build_ai_plugin_settings([empty_provider], {})

    # Пустые actions → плагин остаётся в пользовательском режиме.
    assert out["actions"] == {}
    assert out["providers"] == {}
    assert out["models"] == []
