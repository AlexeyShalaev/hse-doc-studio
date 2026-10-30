from __future__ import annotations

from dataclasses import dataclass, replace

from hse_doc_studio.core.remote_runner import (
    IRemoteRunnerSupervisor,
    RemoteAiEndpointChoice,
    RemoteRunnerStatusInfo,
    cloud_flavor,
)
from hse_doc_studio.core.repositories import IAIProviderRepository


@dataclass(frozen=True)
class UpdateRemoteRunnerInput:
    """None значит «не менять»: интерфейс шлёт только то, что человек тронул."""

    enabled: bool | None = None
    server_url: str | None = None
    name: str | None = None
    concurrency: int | None = None
    yield_to_local: bool | None = None
    ai_endpoints: tuple[RemoteAiEndpointChoice, ...] | None = None


class UpdateRemoteRunnerUC:
    """Частичная правка настроек облачных сборок поверх текущих; перезапуск цикла решает супервизор."""

    def __init__(self, supervisor: IRemoteRunnerSupervisor, providers: IAIProviderRepository) -> None:
        self._supervisor = supervisor
        self._providers = providers

    async def execute(self, data: UpdateRemoteRunnerInput) -> RemoteRunnerStatusInfo:
        current = self._supervisor.status().settings
        names = [choice.name for choice in data.ai_endpoints or ()]
        if len(set(names)) != len(names):
            raise ValueError("AI endpoint names must be unique")
        if data.ai_endpoints:
            await self._check_providers(data.ai_endpoints)
        updated = replace(
            current,
            enabled=current.enabled if data.enabled is None else data.enabled,
            server_url=current.server_url if data.server_url is None else data.server_url,
            name=current.name if data.name is None else data.name,
            concurrency=current.concurrency if data.concurrency is None else data.concurrency,
            yield_to_local=current.yield_to_local if data.yield_to_local is None else data.yield_to_local,
            ai_endpoints=current.ai_endpoints if data.ai_endpoints is None else data.ai_endpoints,
        )
        await self._supervisor.apply(updated)
        return self._supervisor.status()

    async def _check_providers(self, choices: tuple[RemoteAiEndpointChoice, ...]) -> None:
        """Открыть облаку можно только свой локальный провайдер: Ollama или OpenAI-совместимый адрес в своей сети."""
        by_id = {str(p.id): p for p in await self._providers.list_all()}
        for choice in choices:
            provider = by_id.get(choice.provider_id)
            if provider is None:
                raise ValueError(f"AI provider {choice.provider_id} not found")
            if cloud_flavor(provider.type.value, provider.base_url) is None:
                raise ValueError(f"AI provider {provider.name} cannot be opened to the cloud")
