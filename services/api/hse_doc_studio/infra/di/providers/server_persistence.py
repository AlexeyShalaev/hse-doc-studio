"""Провайдер хранения серверного режима (Postgres).

Модуль тянет sqlalchemy, поэтому подключается лениво, только из ``create_container(server)``.
Репозитории регистрируются здесь по мере готовности срезов и перекрывают локальные через
``override=True``; пока их нет, серверный контейнер берёт остальное у ``LocalPersistenceProvider``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import timedelta

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from hse_doc_studio.api.config import ServerConfig, settings
from hse_doc_studio.core.git_sync.fetch_schedule import FetchBook
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry, IGitRemoteRegistry
from hse_doc_studio.core.projects.lifecycle import ServerProjectStorage
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.repositories import IProjectIndexRepository, IProjectRepository, ITemplateRepository
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.core.vcs.protocols import IVcsService
from hse_doc_studio.infra.db.engine import create_engine, create_sessionmaker
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer
from hse_doc_studio.infra.projects.catalog_sync import (
    MirroringProjectRepository,
    ProjectCatalogMirror,
    ProjectCatalogReconciler,
)
from hse_doc_studio.infra.projects.purge import ProjectPurger
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.secrets.server_keys import server_key_store
from hse_doc_studio.use_cases.projects.create_project import CreateProjectUC
from hse_doc_studio.use_cases.projects.unregister_project import UnregisterProjectUC
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService


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

    @provide
    def get_project_purger(
        self, sessions: SessionProvider, volume: IProjectVolume, server_config: ServerConfig
    ) -> ProjectPurger:
        return ProjectPurger(sessions, volume, timedelta(days=server_config.project_retention_days))

    @provide
    def get_server_project_storage(
        self, volume: IProjectVolume, locator: IProjectLocator, uow: IUnitOfWork
    ) -> ServerProjectStorage:
        return ServerProjectStorage(volume=volume, locator=locator, uow=uow)

    @provide(scope=Scope.REQUEST, override=True)
    def get_create_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        template_service: ProjectTemplateService,
        template_renderer: TemplateRenderer,
        vcs_service: IVcsService,
        base_service: TemplateBaseService,
        storage: ServerProjectStorage,
    ) -> CreateProjectUC:
        return CreateProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            template_repo=template_repo,
            template_service=template_service,
            template_renderer=template_renderer,
            vcs_service=vcs_service,
            base_service=base_service,
            server_storage=storage,
        )

    @provide(scope=Scope.REQUEST, override=True)
    def get_unregister_project_uc(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        git_operations: IGitOperationRegistry,
        git_remotes: IGitRemoteRegistry,
        book: FetchBook,
        storage: ServerProjectStorage,
    ) -> UnregisterProjectUC:
        return UnregisterProjectUC(
            project_repo=project_repo,
            project_index_repo=project_index_repo,
            git_operations=git_operations,
            git_remotes=git_remotes,
            fetch_book=book,
            server_storage=storage,
        )
