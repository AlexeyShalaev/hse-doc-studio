from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAIProviderRepository


@dataclass
class CreateAIProviderInput:
    name: str
    type: AIProviderType
    api_key: str
    base_url: str = ""
    models: list[str] = field(default_factory=list)
    ssl_verify: bool = True
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 60.0


@dataclass
class CreateAIProviderOutput:
    provider: AIProvider


class CreateAIProviderUC:
    def __init__(self, ai_provider_repo: IAIProviderRepository) -> None:
        self._repo = ai_provider_repo

    async def execute(self, inp: CreateAIProviderInput) -> CreateAIProviderOutput:
        name = inp.name.strip()
        if not name:
            raise ValueError(localized_error("укажите название", "name is required"))
        if not inp.api_key.strip():
            raise ValueError(localized_error("укажите API-ключ", "api_key is required"))
        if inp.connect_timeout_s <= 0 or inp.request_timeout_s <= 0:
            raise ValueError(localized_error("таймауты должны быть положительными", "timeouts must be positive"))
        provider = AIProvider(
            id=uuid4(),
            name=name,
            type=inp.type,
            api_key=inp.api_key.strip(),
            base_url=inp.base_url.strip(),
            models=list(inp.models),
            created_at=datetime.now(timezone.utc),
            ssl_verify=inp.ssl_verify,
            connect_timeout_s=inp.connect_timeout_s,
            request_timeout_s=inp.request_timeout_s,
        )
        self._repo.create(provider)
        return CreateAIProviderOutput(provider=provider)
