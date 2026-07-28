from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.ai import IAIModelLister
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAIProviderRepository


@dataclass
class ListProviderModelsInput:
    provider_id: UUID


@dataclass
class ListProviderModelsOutput:
    models: list[str]


class ListProviderModelsUC:
    def __init__(self, ai_provider_repo: IAIProviderRepository, model_lister: IAIModelLister) -> None:
        self._repo = ai_provider_repo
        self._model_lister = model_lister

    async def execute(self, inp: ListProviderModelsInput) -> ListProviderModelsOutput:
        provider = self._repo.get(inp.provider_id)
        if provider is None:
            raise NotFoundError(
                localized_error(f"AI-провайдер {inp.provider_id} не найден", f"AI provider {inp.provider_id} not found")
            )
        models = await self._model_lister.list_models(provider)
        return ListProviderModelsOutput(models=models)
