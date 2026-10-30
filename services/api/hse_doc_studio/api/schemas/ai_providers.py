from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from hse_doc_studio.core.enums import AIProviderType


class CreateAIProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: AIProviderType
    # У вида `runner` ключа и адреса нет: оба пустые.
    api_key: str
    base_url: str = ""
    models: list[str] = Field(default_factory=list)
    ssl_verify: bool = True
    connect_timeout_s: float = Field(default=10.0, gt=0, le=300)
    request_timeout_s: float = Field(default=60.0, gt=0, le=600)
    # Вид `runner`: свой раннер и имя ИИ-адреса, объявленного им.
    runner_id: str | None = None
    runner_endpoint: str | None = Field(default=None, max_length=32)


class UpdateAIProviderRequest(BaseModel):
    # All optional: omitted (or null) field = keep current value. A blank
    # `api_key` also means "keep" — the stored key is never sent to the client,
    # so the form leaves it empty unless the user wants to replace it.
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    type: AIProviderType | None = None
    api_key: str | None = None
    base_url: str | None = None
    models: list[str] | None = None
    ssl_verify: bool | None = None
    connect_timeout_s: float | None = Field(default=None, gt=0, le=300)
    request_timeout_s: float | None = Field(default=None, gt=0, le=600)
    runner_id: str | None = None
    runner_endpoint: str | None = Field(default=None, max_length=32)


class AiProviderRelay(BaseModel):
    """Через какой раннер и адрес идёт провайдер и готова ли ретрансляция сейчас."""

    model_config = ConfigDict(extra="forbid")

    runner_id: str
    runner_name: str | None
    endpoint: str
    flavor: Literal["openai", "ollama"]
    state: Literal["ready", "runner_offline", "runner_paused", "runner_revoked", "endpoint_missing", "disabled"]


class AIProviderResponse(BaseModel):
    # Deliberately omits `api_key`: only `has_api_key` is exposed so the secret
    # never crosses to the browser.
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    type: AIProviderType
    base_url: str
    models: list[str]
    has_api_key: bool
    created_at: datetime
    ssl_verify: bool
    connect_timeout_s: float
    request_timeout_s: float
    # Общий провайдер установки: его задал админ, ключ пользователю не виден. В локальном режиме всегда false.
    shared: bool = False
    # Откуда провайдер: свой, организации, установки (`shared == (source == "instance")`).
    source: Literal["own", "org", "instance"] = "own"
    relay: AiProviderRelay | None = None


class ProviderModelsResponse(BaseModel):
    models: list[str]
