from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAIProviderRepository


@dataclass
class GetAIProviderInput:
    provider_id: UUID


@dataclass
class GetAIProviderOutput:
    provider: AIProvider


class GetAIProviderUC:
    def __init__(self, ai_provider_repo: IAIProviderRepository) -> None:
        self._repo = ai_provider_repo

    async def execute(self, inp: GetAIProviderInput) -> GetAIProviderOutput:
        provider = self._repo.get(inp.provider_id)
        if provider is None:
            raise NotFoundError(
                localized_error(f"AI-провайдер {inp.provider_id} не найден", f"AI provider {inp.provider_id} not found")
            )
        return GetAIProviderOutput(provider=provider)
