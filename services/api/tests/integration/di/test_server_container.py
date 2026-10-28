"""Смоук DI: режим выбирает провайдеры, local не меняется, server собирается с подставным engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from dishka.exceptions import NoFactoryError
from hse_doc_studio.api.config import ServerConfig, settings
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.repositories import IProjectRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.use_cases.projects.get_project import GetProjectUC

pytest.importorskip("sqlalchemy")


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "host_data_dir", None)


async def test__local_container__has_no_server_ports() -> None:
    container = create_container(StudioMode.local)
    try:
        async with container() as request:
            repo = await request.get(IProjectRepository)
            with pytest.raises(NoFactoryError):
                await request.get(IUnitOfWork)
    finally:
        await container.close()

    assert isinstance(repo, JsonProjectRepository)


async def test__server_container__fake_engine__resolves_uow_config_and_use_cases() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")  # ленивый, соединения не откроет
    container = create_container(StudioMode.server, engine=engine)
    try:
        async with container() as request:
            uow = await request.get(IUnitOfWork)
            server_cfg = await request.get(ServerConfig)
            get_project = await request.get(GetProjectUC)
    finally:
        await container.close()
        await engine.dispose()

    assert hasattr(uow, "begin")
    assert server_cfg.projects_root == Path(settings.data_dir) / "projects"
    assert isinstance(get_project, GetProjectUC)


async def test__server_container__resolves_actor_resolver_chain() -> None:
    from hse_doc_studio.core.identity.protocols import IActorResolver
    from hse_doc_studio.infra.identity.resolvers import ChainActorResolver
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    container = create_container(StudioMode.server, engine=engine)
    try:
        resolver = await container.get(IActorResolver)
    finally:
        await container.close()
        await engine.dispose()

    assert isinstance(resolver, ChainActorResolver)


def test__local_container__does_not_import_server_modules() -> None:
    for name in list(sys.modules):
        if name.startswith("hse_doc_studio.infra.di.providers.server_"):
            del sys.modules[name]

    create_container(StudioMode.local)

    assert "hse_doc_studio.infra.di.providers.server_persistence" not in sys.modules


async def test__server_container__resolves_postgres_project_locator_and_volume() -> None:
    from hse_doc_studio.core.projects.locator import IProjectLocator
    from hse_doc_studio.core.projects.volume import IProjectVolume
    from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
    from hse_doc_studio.infra.projects.catalog_sync import MirroringProjectRepository, ProjectCatalogReconciler
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    container = create_container(StudioMode.server, engine=engine)
    try:
        async with container() as request:
            locator = await request.get(IProjectLocator)
            volume = await request.get(IProjectVolume)
            repo = await request.get(IProjectRepository)
            reconciler = await request.get(ProjectCatalogReconciler)
    finally:
        await container.close()
        await engine.dispose()

    assert isinstance(locator, PostgresProjectLocator)
    assert isinstance(repo, MirroringProjectRepository)
    assert isinstance(reconciler, ProjectCatalogReconciler)
    assert volume.root == Path(settings.data_dir) / "projects"
