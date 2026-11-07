"""Общий ИИ-провайдер для сервера моделей: запись в тех же таблицах, что и у админки провайдеров.

Установка идёт в фоне, вне запроса, поэтому записи ведутся в собственном скоупе контейнера DI со своей транзакцией.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from dishka import AsyncContainer

from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.model_servers import RegisteredProvider
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.ops_ai_providers import InstanceAiProvider, InstanceAiProviderStore

_CONNECT_TIMEOUT_S = 10.0
_REQUEST_TIMEOUT_S = 120.0


class ContainerProviderRegistry:
    def __init__(self, container: AsyncContainer) -> None:
        self._container = container

    async def register(  # noqa: PLR0913 — поля провайдера
        self,
        admin_id: str,
        *,
        provider_id: UUID,
        name: str,
        type: AIProviderType,
        base_url: str,
        api_key: str,
        models: tuple[str, ...],
    ) -> RegisteredProvider:
        provider = InstanceAiProvider(
            id=provider_id,
            name=name,
            type=type,
            base_url=base_url,
            models=models,
            ssl_verify=True,
            connect_timeout_s=_CONNECT_TIMEOUT_S,
            request_timeout_s=_REQUEST_TIMEOUT_S,
            created_at=datetime.now(UTC),
            key_set=bool(api_key),
        )
        async with self._container() as scope:
            store = await scope.get(InstanceAiProviderStore)
            uow = await scope.get(IUnitOfWork)
            audit = await scope.get(IAuditLog)
            async with uow.begin():
                await store.save(provider, api_key=api_key)
                await audit.record(
                    "settings.ai_provider_create",
                    actor_id=admin_id,
                    target=str(provider_id),
                    details={"name": name, "type": type.value, "source": "model_server"},
                )
        return RegisteredProvider(provider_id, name)

    async def unregister(self, admin_id: str, provider_id: UUID) -> None:
        async with self._container() as scope:
            store = await scope.get(InstanceAiProviderStore)
            uow = await scope.get(IUnitOfWork)
            audit = await scope.get(IAuditLog)
            async with uow.begin():
                await store.delete(provider_id)
                await audit.record(
                    "settings.ai_provider_delete",
                    actor_id=admin_id,
                    target=str(provider_id),
                    details={"source": "model_server"},
                )
