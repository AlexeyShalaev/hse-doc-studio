from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAIProviderRepository


@dataclass
class UpdateAIProviderInput:
    provider_id: UUID
    name: str | None = None
    type: AIProviderType | None = None
    # None or blank → keep the stored key (the UI sends blank to mean "unchanged",
    # since the existing key is never sent back to the browser).
    api_key: str | None = None
    base_url: str | None = None
    models: list[str] | None = None
    # None → keep the stored value (PATCH semantics).
    ssl_verify: bool | None = None
    connect_timeout_s: float | None = None
    request_timeout_s: float | None = None


@dataclass
class UpdateAIProviderOutput:
    provider: AIProvider


class UpdateAIProviderUC:
    def __init__(self, ai_provider_repo: IAIProviderRepository) -> None:
        self._repo = ai_provider_repo

    async def execute(self, inp: UpdateAIProviderInput) -> UpdateAIProviderOutput:
        existing = self._repo.get(inp.provider_id)
        if existing is None:
            raise NotFoundError(
                localized_error(f"AI-провайдер {inp.provider_id} не найден", f"AI provider {inp.provider_id} not found")
            )

        name = existing.name if inp.name is None else inp.name.strip()
        if not name:
            raise ValueError(localized_error("укажите название", "name is required"))

        # Blank/omitted key → keep the stored one (never sent back to the client).
        api_key = existing.api_key
        if inp.api_key is not None and inp.api_key.strip():
            api_key = inp.api_key.strip()

        connect_timeout_s = existing.connect_timeout_s if inp.connect_timeout_s is None else inp.connect_timeout_s
        request_timeout_s = existing.request_timeout_s if inp.request_timeout_s is None else inp.request_timeout_s
        if connect_timeout_s <= 0 or request_timeout_s <= 0:
            raise ValueError(localized_error("таймауты должны быть положительными", "timeouts must be positive"))

        updated = AIProvider(
            id=existing.id,
            name=name,
            type=existing.type if inp.type is None else inp.type,
            api_key=api_key,
            base_url=existing.base_url if inp.base_url is None else inp.base_url.strip(),
            models=existing.models if inp.models is None else list(inp.models),
            created_at=existing.created_at,
            ssl_verify=existing.ssl_verify if inp.ssl_verify is None else inp.ssl_verify,
            connect_timeout_s=connect_timeout_s,
            request_timeout_s=request_timeout_s,
        )
        self._repo.update(updated)
        return UpdateAIProviderOutput(provider=updated)
