from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.repositories import IAIProviderRepository


@dataclass
class ListAIProvidersOutput:
    providers: list[AIProvider]


class ListAIProvidersUC:
    def __init__(self, ai_provider_repo: IAIProviderRepository) -> None:
        self._repo = ai_provider_repo

    async def execute(self) -> ListAIProvidersOutput:
        return ListAIProvidersOutput(providers=self._repo.list_all())
