from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from hse_doc_studio.core.ai_runtime import IOllamaRuntime
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.repositories import IAIProviderRepository


@dataclass
class SyncLocalProviderResult:
    provider_id: UUID | None
    models: list[str]


class SyncLocalOllamaProviderUC:
    """Keep a single auto-managed `ollama`-type AI provider in sync with the runtime.

    After a pull/delete (or on start) this upserts one provider record pointing
    at the live local OpenAI-compatible endpoint (``<base>/v1``) with its model
    list mirrored from the runtime — so the local models appear in the global
    "default provider/model" picker and the future agent dispatch, unchanged.
    The record carries no api_key and is rendered read-only in the UI.
    """

    def __init__(
        self,
        runtime: IOllamaRuntime,
        ai_provider_repo: IAIProviderRepository,
        provider_name: str,
    ) -> None:
        self._runtime = runtime
        self._ai_provider_repo = ai_provider_repo
        self._provider_name = provider_name

    async def execute(self) -> SyncLocalProviderResult:
        status = await self._runtime.status()
        existing = next(
            (p for p in self._ai_provider_repo.list_all() if p.type == AIProviderType.ollama),
            None,
        )

        # Runtime is down: we can't list models, so DON'T clobber the record's
        # known model list (the models still live in the Docker volume). Leave
        # any existing record untouched and never create a dangling one.
        if status.base_url is None:
            return SyncLocalProviderResult(
                provider_id=existing.id if existing else None,
                models=existing.models if existing else [],
            )

        openai_base = f"{status.base_url.rstrip('/')}/v1"
        models = status.installed_models

        if existing is not None:
            updated = AIProvider(
                id=existing.id,
                name=existing.name,
                type=AIProviderType.ollama,
                api_key="",
                base_url=openai_base,
                models=models,
                created_at=existing.created_at,
                ssl_verify=existing.ssl_verify,
                connect_timeout_s=existing.connect_timeout_s,
                request_timeout_s=existing.request_timeout_s,
            )
            self._ai_provider_repo.update(updated)
            return SyncLocalProviderResult(provider_id=existing.id, models=models)

        created = AIProvider(
            id=uuid4(),
            name=self._provider_name,
            type=AIProviderType.ollama,
            api_key="",
            base_url=openai_base,
            models=models,
            created_at=datetime.now(timezone.utc),
        )
        self._ai_provider_repo.create(created)
        return SyncLocalProviderResult(provider_id=created.id, models=models)
