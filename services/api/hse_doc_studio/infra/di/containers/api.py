from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import AsyncContainer, Provider, make_async_container
from dishka.integrations.fastapi import FastapiProvider

from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.infra.di.providers.repositories import LocalPersistenceProvider
from hse_doc_studio.infra.di.providers.services import DomainServiceProvider
from hse_doc_studio.infra.di.providers.use_cases import UseCaseProvider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


def _server_providers(engine: AsyncEngine | None) -> list[Provider]:
    # Лениво: серверные модули тянут sqlalchemy, а локальная сборка живёт без extra server.
    from hse_doc_studio.infra.di.providers.server_identity import ServerIdentityProvider  # noqa: PLC0415
    from hse_doc_studio.infra.di.providers.server_jobs import ServerJobsProvider  # noqa: PLC0415
    from hse_doc_studio.infra.di.providers.server_persistence import ServerPersistenceProvider  # noqa: PLC0415

    return [ServerPersistenceProvider(engine), ServerIdentityProvider(), ServerJobsProvider()]


def create_container(mode: StudioMode = StudioMode.local, *, engine: AsyncEngine | None = None) -> AsyncContainer:
    """Контейнер под режим. Серверные провайдеры идут после локальных и перекрывают их; ``engine`` для тестов."""
    providers: list[Provider] = [LocalPersistenceProvider(), DomainServiceProvider(), UseCaseProvider()]
    if mode is StudioMode.server:
        providers.extend(_server_providers(engine))
    providers.append(FastapiProvider())
    return make_async_container(*providers)
