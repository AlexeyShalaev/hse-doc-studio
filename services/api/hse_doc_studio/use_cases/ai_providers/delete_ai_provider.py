from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import IAIProviderRepository, ISettingsRepository

_DEFAULT_PROVIDER_KEY = "default_ai_provider_id"
_DEFAULT_MODEL_KEY = "default_ai_model"


@dataclass
class DeleteAIProviderInput:
    provider_id: UUID


class DeleteAIProviderUC:
    def __init__(self, ai_provider_repo: IAIProviderRepository, settings_repo: ISettingsRepository) -> None:
        self._repo = ai_provider_repo
        self._settings_repo = settings_repo

    async def execute(self, inp: DeleteAIProviderInput) -> None:
        deleted = self._repo.delete(inp.provider_id)
        if not deleted:
            raise NotFoundError(
                localized_error(f"AI-провайдер {inp.provider_id} не найден", f"AI provider {inp.provider_id} not found")
            )
        # Clear the global default if it pointed at the deleted provider, so the
        # stored settings never dangle on a non-existent provider.
        stored = self._settings_repo.get()
        if stored.get(_DEFAULT_PROVIDER_KEY) == str(inp.provider_id):
            stored[_DEFAULT_PROVIDER_KEY] = None
            stored[_DEFAULT_MODEL_KEY] = None
            self._settings_repo.save(stored)
