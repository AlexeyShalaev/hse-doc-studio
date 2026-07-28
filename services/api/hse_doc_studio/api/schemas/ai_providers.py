from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from hse_doc_studio.core.enums import AIProviderType


class CreateAIProviderRequest(BaseModel):
    name: str
    type: AIProviderType
    api_key: str
    base_url: str = ""
    models: list[str] = Field(default_factory=list)
    ssl_verify: bool = True
    connect_timeout_s: float = Field(default=10.0, gt=0, le=300)
    request_timeout_s: float = Field(default=60.0, gt=0, le=600)


class UpdateAIProviderRequest(BaseModel):
    # All optional: omitted (or null) field = keep current value. A blank
    # `api_key` also means "keep" — the stored key is never sent to the client,
    # so the form leaves it empty unless the user wants to replace it.
    name: str | None = None
    type: AIProviderType | None = None
    api_key: str | None = None
    base_url: str | None = None
    models: list[str] | None = None
    ssl_verify: bool | None = None
    connect_timeout_s: float | None = Field(default=None, gt=0, le=300)
    request_timeout_s: float | None = Field(default=None, gt=0, le=600)


class AIProviderResponse(BaseModel):
    # Deliberately omits `api_key`: only `has_api_key` is exposed so the secret
    # never crosses to the browser.
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


class ProviderModelsResponse(BaseModel):
    models: list[str]
