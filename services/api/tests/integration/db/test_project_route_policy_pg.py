from __future__ import annotations

from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.routing import ProjectBuildRunners
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.project_route_policy import SqlProjectRoutePolicyRepository
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.factories.pg_projects import seed_project, seed_user

pytestmark = pytest.mark.pg


async def test__route_policy__defaults_to_shared_and_switches(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    repo = SqlProjectRoutePolicyRepository(sessions)
    owner = await seed_user(sessions)
    project = await seed_project(sessions, owner_user_id=owner)

    info = await repo.get(project)
    assert info is not None
    assert (info.owner_user_id, info.build_runners, info.deleted, info.is_personal) == (
        owner,
        ProjectBuildRunners.shared,
        False,
        True,
    )

    assert await repo.set_build_runners(project, ProjectBuildRunners.owner) is True
    info = await repo.get(project)
    assert info is not None
    assert info.build_runners is ProjectBuildRunners.owner


async def test__route_policy__unknown_project(pg_migrated_engine: AsyncEngine) -> None:
    repo = SqlProjectRoutePolicyRepository(SessionProvider(create_sessionmaker(pg_migrated_engine)))
    assert await repo.get(uuid4()) is None
    assert await repo.set_build_runners(uuid4(), ProjectBuildRunners.owner) is False


async def test__route_policy__deleted_and_ownerless_projects(pg_migrated_engine: AsyncEngine) -> None:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    repo = SqlProjectRoutePolicyRepository(sessions)
    gone = await seed_project(sessions, owner_user_id=await seed_user(sessions), deleted=True)
    ownerless = await seed_project(sessions, owner_user_id=None)

    gone_info, ownerless_info = await repo.get(gone), await repo.get(ownerless)
    assert gone_info is not None
    assert gone_info.deleted is True
    assert ownerless_info is not None
    assert ownerless_info.is_personal is False
