"""«Модели для облака»: выбранные локальные провайдеры как ИИ-адреса раннера Студии.

Сервер получает только имя и вид адреса; адрес и ключ провайдера остаются в этом процессе. Провайдер,
который удалили или который больше не годится облаку (адрес ушёл в публичный интернет), молча выпадает.
"""

from __future__ import annotations

from collections.abc import Callable

from hse_doc_studio.core.remote_runner import RemoteAiEndpointChoice, cloud_flavor
from hse_doc_studio.core.repositories import IAIProviderRepository
from hse_doc_studio.infra.docker.siblings import outbound_url
from hse_doc_studio.infra.remote_runner.session import LocalAiEndpoint


class LocalAiEndpointResolver:
    def __init__(self, providers: IAIProviderRepository) -> None:
        self._providers = providers

    async def __call__(self, choices: tuple[RemoteAiEndpointChoice, ...]) -> tuple[LocalAiEndpoint, ...]:
        by_id = {str(p.id): p for p in await self._providers.list_all()}
        endpoints: list[LocalAiEndpoint] = []
        for choice in choices:
            provider = by_id.get(choice.provider_id)
            if provider is None:
                continue
            flavor = cloud_flavor(provider.type.value, provider.base_url)
            if flavor is None:
                continue
            key = provider.api_key or None
            endpoints.append(
                LocalAiEndpoint(
                    name=choice.name,
                    provider_id=choice.provider_id,
                    base_url=outbound_url(provider.base_url) or provider.base_url,
                    display_url=provider.base_url,
                    flavor=flavor,
                    # Ключ читается при открытии сессии и при каждой правке списка; на сервер он не уходит.
                    api_key=_constant(key),
                )
            )
        return tuple(endpoints)


def _constant(value: str | None) -> Callable[[], str | None]:
    return lambda: value
