"""user_onboarding: строка на пользователя, давние пользователи после миграции получают приглашение."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.access.context import ActorRequired
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.onboarding.entities import OnboardingState, OnboardingStatus
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.onboarding import SqlOnboardingRepository
from hse_doc_studio.infra.db.session import SessionProvider
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_NOW = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


@pytest.fixture
async def repo(pg_migrated_engine: AsyncEngine) -> SqlOnboardingRepository:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for uid in ("anna", "boris"):
        await users.add(make_user(uid))
    return SqlOnboardingRepository(sessions)


async def test__save_then_get__round_trips_and_is_isolated(repo: SqlOnboardingRepository) -> None:
    state = OnboardingState(
        status=OnboardingStatus.in_progress,
        scenario_version=2,
        step="demo.agent",
        answers={"role": "student", "work": "hse-cs-se/vkr"},
        started_at=_NOW,
        updated_at=_NOW,
    )
    with as_actor(Actor.user("anna")):
        await repo.save(state)
        await repo.save(state)
        assert await repo.get() == state
    with as_actor(Actor.user("boris")):
        assert await repo.get() is None


async def test__get__without_actor__raises(repo: SqlOnboardingRepository) -> None:
    with pytest.raises(ActorRequired):
        await repo.get()


async def test__migration__existing_users_become_suggested(pg_engine: AsyncEngine) -> None:
    await migrator.upgrade(pg_engine, "dg_01_diagnostics")
    async with pg_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, email, email_normalized, name, status, created_at) "
                "VALUES ('old', 'old@example.org', 'old@example.org', 'Old', 'active', now())"
            )
        )

    await migrator.upgrade(pg_engine, "ob_01_user_onboarding")

    async with pg_engine.connect() as conn:
        rows = (await conn.execute(text("SELECT user_id, status FROM user_onboarding"))).all()
    assert [tuple(r) for r in rows] == [("old", "suggested")]
    await migrator.downgrade(pg_engine, "dg_01_diagnostics")
    await migrator.upgrade(pg_engine)
    assert await migrator.check_drift(pg_engine) == []
