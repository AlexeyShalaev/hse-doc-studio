"""Провайдер хранения серверного режима (Postgres).

Модуль тянет sqlalchemy, поэтому подключается лениво, только из ``create_container(server)``.
Репозитории регистрируются здесь по мере готовности срезов и перекрывают локальные через
``override=True``; пока их нет, серверный контейнер берёт остальное у ``LocalPersistenceProvider``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hse_doc_studio.api.config import ServerConfig, settings
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.repositories import IProjectRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.db.engine import create_engine, create_sessionmaker
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.catalog_sync import (
    MirroringProjectRepository,
    ProjectCatalogMirror,
    ProjectCatalogReconciler,
)
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.secrets.server_keys import server_key_store


class ServerPersistenceProvider(Provider):
    scope = Scope.APP

    def __init__(self, engine: AsyncEngine | None = None) -> None:
        """``engine`` подставляют тесты: тогда его жизнью владеет вызывающий, контейнер его не закрывает."""
        super().__init__()
        self._engine = engine

    @provide
    def get_server_config(self) -> ServerConfig:
        return ServerConfig.from_settings(settings)

    @provide
    async def get_engine(self) -> AsyncIterator[AsyncEngine]:
        if self._engine is not None:
            yield self._engine
            return
        engine = create_engine(settings.db)
        try:
            yield engine
        finally:
            await engine.dispose()

    @provide
    def get_sessionmaker(self, engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        return create_sessionmaker(engine)

    @provide
    def get_session_provider(self, sessionmaker: async_sessionmaker[AsyncSession]) -> SessionProvider:
        return SessionProvider(sessionmaker)

    @provide
    def get_unit_of_work(self, sessions: SessionProvider) -> IUnitOfWork:
        return SqlUnitOfWork(sessions)

    @provide(override=True)
    def get_git_key_store(self) -> KeyFileStore:
        """В server ключ только из окружения: без него контейнер не создаётся."""
        return server_key_store(settings)

    @provide
    def get_project_volume(self, server_config: ServerConfig) -> IProjectVolume:
        return LocalDiskProjectVolume(server_config.projects_root)

    @provide
    def get_project_catalog_mirror(self, sessions: SessionProvider) -> ProjectCatalogMirror:
        return ProjectCatalogMirror(sessions)

    @provide(override=True)
    def get_project_repo(self, volume: IProjectVolume, mirror: ProjectCatalogMirror) -> IProjectRepository:
        """project.json остаётся источником содержимого; копия name/kind/lang уходит в каталог на каждый save."""
        return MirroringProjectRepository(JsonProjectRepository(), volume, mirror)

    @provide(override=True)
    def get_project_locator(
        self, sessions: SessionProvider, volume: IProjectVolume, projects: IProjectRepository
    ) -> IProjectLocator:
        return PostgresProjectLocator(sessions, volume, projects)

    @provide
    def get_project_catalog_reconciler(
        self, sessions: SessionProvider, volume: IProjectVolume, projects: IProjectRepository
    ) -> ProjectCatalogReconciler:
        return ProjectCatalogReconciler(sessions, volume, projects)
