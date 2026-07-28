from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType

# Формат: серверные настройки AI-плагина ONLYOFFICE (config-ключ `aiSettings`
# Document Server; DocsCoServer отдаёт их редактору как `aiPluginSettings` при
# коннекте, плагин видит их как AI.serverSettings). В серверном режиме кнопка
# Settings у плагина скрыта, а все запросы идут через DS-прокси `/ai-proxy`,
# который сам подставляет api-ключ (в браузер ключи не попадают — DS отдаёт
# providers с key="").
#
# Требования формата (см. sdkjs-plugins/content/ai + server/DocService):
# - хотя бы у одного action должна быть модель, иначе DS считает настройки
#   пустыми и плагин откатывается в пользовательский localStorage-режим;
# - providers: {<имя>: {name, url, key, models: [{id, name, endpoints, options}]}} —
#   имя ищется среди классов провайдеров плагина ("OpenAI", "Anthropic",
#   "Ollama", …); незнакомое имя получает базовый OpenAI-совместимый класс
#   (тогда url должен содержать /v1);
# - models (верхний уровень): UI-список {name, id, provider, capabilities}.

# aiSettings.version текущего DS (плагин мигрирует 3 → свою версию сам).
_SETTINGS_VERSION = 3
# Маршрут AI-прокси в DocService (app.use('/ai-proxy', …) в server.js).
_PROXY_ROUTE = "/ai-proxy"

# Битовые флаги AI.CapabilitiesUI плагина.
_CAP_CHAT = 0x01
# AI.Endpoints.Types.v1.Chat_Completions.
_ENDPOINT_CHAT_COMPLETIONS = 0x01

# Текстовые actions плагина — им назначается модель по умолчанию. Остальные
# (ImageGeneration/OCR/Vision) остаются без модели: наши провайдеры — текстовые.
_TEXT_ACTIONS = ("Chat", "Summarization", "Translation", "TextAnalyze")
_OTHER_ACTIONS = ("ImageGeneration", "OCR", "Vision")

# Хосты, которые изнутри DS-контейнера не резолвятся в хост-машину: контейнер
# запускается с --add-host=host.docker.internal:host-gateway.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}  # noqa: S104 — список для ЗАМЕНЫ, не bind

_ANTHROPIC_DEFAULT_URL = "https://api.anthropic.com"
_OPENAI_DEFAULT_URL = "https://api.openai.com"


def _rewrite_local_host(url: str) -> str:
    """localhost/127.0.0.1 → host.docker.internal (прокси живёт В контейнере DS)."""
    parts = urlsplit(url)
    if parts.hostname and parts.hostname.lower() in _LOCAL_HOSTS:
        host = f"host.docker.internal:{parts.port}" if parts.port else "host.docker.internal"
        parts = parts._replace(netloc=host)
    return urlunsplit(parts)


def _model_detail(model_id: str) -> dict[str, Any]:
    # endpoints обязателен: AI.Request ищет модель в provider.models и решает
    # chat/completions именно по нему.
    return {
        "id": model_id,
        "name": model_id,
        "endpoints": [_ENDPOINT_CHAT_COMPLETIONS],
        "options": {},
    }


def _empty_settings() -> dict[str, Any]:
    # Пустые actions → DS отдаёт редактору "настроек нет" → плагин работает в
    # обычном пользовательском режиме (кнопка Settings видна).
    return {
        "version": _SETTINGS_VERSION,
        "proxy": _PROXY_ROUTE,
        "actions": {},
        "providers": {},
        "models": [],
        "customProviders": {},
    }


def _plugin_provider_entry(provider: AIProvider, taken_names: set[str]) -> tuple[str, str] | None:
    """(имя-для-плагина, url) или None, когда провайдер выразить нельзя.

    `claude` обязан называться "Anthropic" (иначе плагин применит базовый
    OpenAI-совместимый протокол к api.anthropic.com); второй claude-провайдер
    выразить нечем — пропускается. `openai` предпочитает класс "OpenAI";
    занято — кастомное имя с базовым классом (протокол тот же, но url должен
    содержать /v1). `openai_compat`/`ollama` — кастомное имя / класс "Ollama".
    """
    if provider.type == AIProviderType.claude:
        if "Anthropic" in taken_names:
            return None
        return "Anthropic", provider.base_url or _ANTHROPIC_DEFAULT_URL
    if provider.type == AIProviderType.ollama:
        name = "Ollama" if "Ollama" not in taken_names else _unique_name(provider.name, taken_names)
        return name, provider.base_url
    if provider.type == AIProviderType.openai:
        if "OpenAI" not in taken_names:
            return "OpenAI", provider.base_url or _OPENAI_DEFAULT_URL
        base = provider.base_url or f"{_OPENAI_DEFAULT_URL}/v1"
        return _unique_name(provider.name, taken_names), base
    # openai_compat: базовый класс плагина, url провайдера уже содержит /v1
    # (конвенция OpenAI SDK).
    return _unique_name(provider.name, taken_names), provider.base_url


def _unique_name(name: str, taken: set[str]) -> str:
    candidate = name.strip() or "Provider"
    n = 2
    while candidate in taken:
        candidate = f"{name} ({n})"
        n += 1
    return candidate


def _map_provider(out: dict[str, Any], provider: AIProvider) -> bool:
    """Добавить провайдера в aiSettings; False — выразить в плагине нечем."""
    entry = _plugin_provider_entry(provider, set(out["providers"].keys()))
    if entry is None:
        return False
    name, url = entry
    url = _rewrite_local_host(url.strip().rstrip("/"))
    if not url:
        return False
    out["providers"][name] = {
        "name": name,
        "url": url,
        "key": provider.api_key,
        "models": [_model_detail(m) for m in provider.models],
    }
    out["models"].extend(
        {"name": f"{name} [{m}]", "id": m, "provider": name, "capabilities": _CAP_CHAT} for m in provider.models
    )
    return True


def _resolve_default_model(mapped: list[AIProvider], app_settings: dict[str, Any]) -> str:
    """Дефолт приложения (default_ai_provider_id/default_ai_model), если он
    попал в выгрузку; иначе первая модель первого провайдера."""
    default_provider_id = str(app_settings.get("default_ai_provider_id") or "")
    wanted = app_settings.get("default_ai_model")
    for provider in mapped:
        if str(provider.id) == default_provider_id and isinstance(wanted, str) and wanted in provider.models:
            return wanted
    return mapped[0].models[0]


def build_ai_plugin_settings(
    providers: list[AIProvider],
    app_settings: dict[str, Any],
) -> dict[str, Any]:
    """Наши AI-провайдеры → серверные настройки AI-плагина Document Server.

    Провайдеры без моделей пропускаются (плагину нечего показать). Нет ни одной
    модели → пустые настройки (плагин остаётся в пользовательском режиме).
    """
    out = _empty_settings()
    # _map_provider попутно наполняет out — фильтр оставляет только то, что
    # реально удалось выразить в терминах плагина.
    mapped = [p for p in providers if p.models and _map_provider(out, p)]

    if not mapped:
        return _empty_settings()

    default_model = _resolve_default_model(mapped, app_settings)
    for action in _TEXT_ACTIONS:
        out["actions"][action] = {"model": default_model}
    for action in _OTHER_ACTIONS:
        out["actions"][action] = {"model": ""}
    return out
