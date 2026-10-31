"""Счётчики расхода и расход по таблицам проектов в Postgres: атомарное прибавление, сброс периода, суммы владельцев."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.jobs.quotas import QuotaOverride, QuotaOwnerKind, QuotaResource
from hse_doc_studio.core.projects.usage import ProjectUsage
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.job_quotas import SqlQuotaOverrideRepository
from hse_doc_studio.infra.db.repositories.project_usage import PostgresProjectUsageStore
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.repositories.usage_counters import SqlOwnerFootprint, SqlUsageCounters
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.factories import make_document, make_project
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")
_NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
_START = date(2026, 11, 1)


class World:
    def __init__(self, sessions: SessionProvider, tmp_path: Path) -> None:
        self.sessions = sessions
        volume = LocalDiskProjectVolume(tmp_path / "projects")
        self.volume = volume
        self.projects = JsonProjectRepository()
        self.locator = PostgresProjectLocator(sessions, volume, self.projects)
        self.counters = SqlUsageCounters(sessions)
        self.footprint = SqlOwnerFootprint(sessions)
        self.usage = PostgresProjectUsageStore(sessions)

    async def add_project(self) -> object:
        project_id = uuid4()
        folder = self.volume.allocate(project_id)
        self.projects.save(replace(make_project(folder=folder, documents=[make_document()]), id=project_id))
        with as_actor(_ANNA):
            await self.locator.register(folder)
        return project_id


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    await SqlUserRepository(sessions).add(make_user("anna"))
    return World(sessions, tmp_path)


async def test__counters__add_accumulates_and_new_period_starts_from_zero(world: World) -> None:
    kind, user = QuotaKind.ai_tokens_month, QuotaOwnerKind.user

    assert await world.counters.add(user, "u1", kind, _START, 30) == 30
    assert await world.counters.add(user, "u1", kind, _START, 12) == 42
    assert await world.counters.get(user, "u1", kind, date(2026, 12, 1)) == 0
    assert await world.counters.get(user, "u1", kind, _START) == 42


async def test__counters__bigint_values_do_not_overflow(world: World) -> None:
    await world.counters.add(QuotaOwnerKind.user, "u1", QuotaKind.ai_tokens_month, _START, 5_000_000_000)

    assert await world.counters.get(QuotaOwnerKind.user, "u1", QuotaKind.ai_tokens_month, _START) == 5_000_000_000


async def test__counters__reset_total_top_and_prune(world: World) -> None:
    kind, user, org = QuotaKind.builds, QuotaOwnerKind.user, QuotaOwnerKind.org
    await world.counters.add(user, "u1", kind, _START, 5)
    await world.counters.add(user, "u2", kind, _START, 9)
    await world.counters.add(org, "o1", kind, _START, 14)
    await world.counters.add(user, "u1", kind, date(2025, 1, 1), 3)

    assert await world.counters.total(kind, _START) == 14
    assert [item.owner_id for item in await world.counters.top(kind, _START, user, 5)] == ["u2", "u1"]
    assert await world.counters.reset(user, "u2", kind, _START) is True
    assert await world.counters.reset(user, "u2", kind, _START) is False
    assert await world.counters.prune(date(2026, 1, 1)) == 1
    assert await world.counters.total(kind, _START) == 5


async def test__footprint__owner_storage_and_members(world: World) -> None:
    project_id = await world.add_project()
    await world.usage.save(ProjectUsage(project_id, 100, 20, 3, _NOW))  # type: ignore[arg-type]

    owner = await world.footprint.project_owner(project_id)  # type: ignore[arg-type]
    assert owner is not None
    assert owner.user_id == "anna"
    assert owner.org_id is None
    assert await world.footprint.storage_bytes(QuotaOwnerKind.user, "anna") == 123
    assert await world.footprint.storage_bytes(QuotaOwnerKind.user, "nobody") == 0
    assert await world.footprint.storage_bytes(QuotaOwnerKind.org, "anna") == 0
    assert await world.footprint.storage_total() == 123
    assert await world.footprint.member_count(project_id) >= 1  # type: ignore[arg-type]
    assert await world.footprint.max_members(QuotaOwnerKind.user, "anna") >= 1
    assert await world.footprint.project_owner(uuid4()) is None


async def test__override_repository__keeps_values_above_32_bits(world: World) -> None:
    repo = SqlQuotaOverrideRepository(world.sessions)
    big = 50 * 1024**3

    await repo.set(QuotaOverride(QuotaOwnerKind.user, "anna", QuotaResource.storage_user, big))
    await repo.set(QuotaOverride(QuotaOwnerKind.org, "o1", QuotaResource.builds_org, 7))

    stored = {(o.owner_id, o.resource): o.hard_limit for o in await repo.list_all()}
    assert stored[("anna", QuotaResource.storage_user)] == big
    await repo.delete(QuotaOwnerKind.org, "o1", QuotaResource.builds_org)
    assert ("o1", QuotaResource.builds_org) not in {(o.owner_id, o.resource) for o in await repo.list_all()}
