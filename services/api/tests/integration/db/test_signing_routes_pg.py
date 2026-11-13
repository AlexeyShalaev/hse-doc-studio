"""SqlSigningRouteRepository на настоящем Postgres: миграция, гонки подписантов, блокировка строки, каскад.

Поведение, общее с InMemory, проверяет контракт (tests/contract/test_signing_route_contract.py); здесь то, что
есть только у базы: одновременные транзакции, точка сохранения внутри транзакции сценария, внешние ключи.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic.script import ScriptDirectory
from hse_doc_studio.core.signing_route.entities import EventKind, RouteStatus, SigningRoute
from hse_doc_studio.core.signing_route.repositories import (
    DocumentOnRouteError,
    OpenRouteExistsError,
    StaleRouteError,
)
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.repositories.signing_routes import SqlSigningRouteRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.db.uow import SqlUnitOfWork
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.factories.pg_projects import seed_project, seed_user
from tests.factories.signing_routes import DOC, make_event, make_full_route, make_route

pytestmark = pytest.mark.pg

_REVISION = "sr_01_signing_routes"
_SKIP_REVISION = "sr_11_skip"
_INSERT_USER = text(
    "INSERT INTO users (id, email, email_normalized, name, status, is_instance_admin, created_at) "
    "VALUES ('u1', 'u1@x.org', 'u1@x.org', 'u1', 'active', false, now())"
)
_INSERT_SKIPPED_NOTICE = text(
    "INSERT INTO notifications (id, user_id, kind, payload, created_at) "
    "VALUES ('n1', 'u1', 'signing_skipped', '{}', now())"
)
_TABLES = {"signing_routes", "signing_route_docs", "signing_route_participants", "signing_route_events"}


@dataclass
class World:
    engine: AsyncEngine
    sessions: SessionProvider
    repo: SqlSigningRouteRepository
    uow: SqlUnitOfWork
    project_id: UUID


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    project_id = await seed_project(sessions, owner_user_id=None)
    return World(pg_migrated_engine, sessions, SqlSigningRouteRepository(sessions), SqlUnitOfWork(sessions), project_id)


async def _tables(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        return set(await conn.run_sync(lambda c: inspect(c).get_table_names()))


async def _count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        return int((await conn.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one())


# --- миграция ---


async def test__migration__upgrade_and_downgrade__creates_and_drops_tables(pg_engine: AsyncEngine) -> None:
    previous = ScriptDirectory.from_config(migrator._config()).get_revision(_REVISION).down_revision
    assert isinstance(previous, str)
    await migrator.upgrade(pg_engine, previous)
    assert not _TABLES & await _tables(pg_engine)

    await migrator.upgrade(pg_engine, _REVISION)
    assert await _tables(pg_engine) >= _TABLES
    # Модель пишет все нынешние колонки (`skipped` у участников из sr_11_skip), поэтому маршрут кладём на полной схеме.
    await migrator.upgrade(pg_engine)
    sessions = SessionProvider(create_sessionmaker(pg_engine))
    project_id = await seed_project(sessions, owner_user_id=None)
    route = make_full_route(project_id)
    await SqlSigningRouteRepository(sessions).add(route, events=[make_event(route)])

    await migrator.downgrade(pg_engine, previous)
    assert not _TABLES & await _tables(pg_engine)
    assert await _count(pg_engine, "projects") == 1

    await migrator.upgrade(pg_engine)
    assert await migrator.check_drift(pg_engine) == []


async def test__skipped__stored_as_sql_null_when_absent_and_round_trips_when_set(world: World) -> None:
    """sr_11_skip: у непропущенных участников в колонке настоящий NULL, пропуск читается так же, как записан."""
    route = await world.repo.add(make_full_route(world.project_id))

    stored = await world.repo.get(world.project_id, route.id)

    assert stored == route
    assert sum(p.skipped is not None for p in stored.participants) == 1
    assert await _count(world.engine, "signing_route_participants WHERE skipped IS NULL") == len(route.participants) - 1


async def test__migration__sr_11_skip__widens_notification_kinds_and_keeps_existing_rows(
    pg_engine: AsyncEngine,
) -> None:
    """Новая колонка nullable, вид `signing_skipped` проходит проверку только после миграции, схема без дрейфа."""
    previous = ScriptDirectory.from_config(migrator._config()).get_revision(_SKIP_REVISION).down_revision
    assert isinstance(previous, str)
    await migrator.upgrade(pg_engine, previous)
    async with pg_engine.begin() as conn:
        await conn.execute(_INSERT_USER)
    with pytest.raises(IntegrityError, match="ck_notifications_kind"):
        async with pg_engine.begin() as conn:
            await conn.execute(_INSERT_SKIPPED_NOTICE)

    await migrator.upgrade(pg_engine, _SKIP_REVISION)

    async with pg_engine.begin() as conn:
        await conn.execute(_INSERT_SKIPPED_NOTICE)
    # Дрейф сверяется с нынешними моделями, поэтому на head: колонки следующих ревизий (dl_01) моделям уже известны.
    await migrator.upgrade(pg_engine)
    assert await migrator.check_drift(pg_engine) == []
    await migrator.downgrade(pg_engine, previous)
    assert await _count(pg_engine, "users") == 1
    assert await _count(pg_engine, "notifications") == 0  # вид, которого прежняя проверка не знает, откат удаляет


# --- гонки ---


async def test__save__two_signers_from_same_version__one_wins_other_stale(world: World) -> None:
    route = await world.repo.add(make_route(world.project_id, status=RouteStatus.active))
    both_read = asyncio.Barrier(2)

    async def act(message: str) -> SigningRoute:
        async with world.uow.begin():
            seen = await world.repo.get(world.project_id, route.id)
            assert seen is not None
            await both_read.wait()
            return await world.repo.save(replace(seen, message=message), events=[make_event(seen, EventKind.approved)])

    results = await asyncio.gather(act("первый"), act("второй"), return_exceptions=True)

    winners = [r for r in results if isinstance(r, SigningRoute)]
    assert len(winners) == 1
    assert sum(isinstance(r, StaleRouteError) for r in results) == 1
    assert await world.repo.get(world.project_id, route.id) == winners[0]
    assert len(await world.repo.list_events(route.id)) == 1


async def test__get_lock__second_locker_waits_for_first_commit(world: World) -> None:
    route = await world.repo.add(make_route(world.project_id, status=RouteStatus.active))
    locked, release = asyncio.Event(), asyncio.Event()

    async def holder() -> None:
        async with world.uow.begin():
            seen = await world.repo.get(world.project_id, route.id, lock=True)
            assert seen is not None
            locked.set()
            await release.wait()
            await world.repo.save(replace(seen, message="первый"))

    async def waiter() -> SigningRoute | None:
        await locked.wait()
        async with world.uow.begin():
            return await world.repo.get(world.project_id, route.id, lock=True)

    first, second = asyncio.create_task(holder()), asyncio.create_task(waiter())
    await locked.wait()
    await asyncio.sleep(0.3)
    blocked = not second.done()
    release.set()
    await first
    seen = await second

    assert blocked
    assert seen is not None
    assert (seen.version, seen.message) == (2, "первый")


async def test__add__concurrent_open_routes_of_checkpoint__one_rejected(world: World) -> None:
    both_ready = asyncio.Barrier(2)

    async def create() -> SigningRoute:
        async with world.uow.begin():
            await both_ready.wait()
            return await world.repo.add(make_route(world.project_id))

    results = await asyncio.gather(create(), create(), return_exceptions=True)

    assert sum(isinstance(r, SigningRoute) for r in results) == 1
    assert sum(isinstance(r, OpenRouteExistsError) for r in results) == 1


async def test__save__concurrent_sends_of_same_document__one_rejected(world: World) -> None:
    drafts = [
        await world.repo.add(make_route(world.project_id, profile_id=profile, docs=(DOC,)))
        for profile in ("topic-approval", "final")
    ]
    both_ready = asyncio.Barrier(2)

    async def send(draft: SigningRoute) -> SigningRoute:
        async with world.uow.begin():
            await both_ready.wait()
            return await world.repo.save(replace(draft, status=RouteStatus.active, round=1))

    results = await asyncio.gather(*(send(d) for d in drafts), return_exceptions=True)

    assert sum(isinstance(r, SigningRoute) for r in results) == 1
    assert sum(isinstance(r, DocumentOnRouteError) for r in results) == 1


# --- транзакция сценария ---


async def test__conflict_inside_scenario_transaction__rolls_back_only_that_write(world: World) -> None:
    async with world.uow.begin():
        first = await world.repo.add(make_route(world.project_id))
        with pytest.raises(OpenRouteExistsError):
            await world.repo.add(make_route(world.project_id), events=[])
        other = await world.repo.add(make_route(world.project_id, profile_id="final"))

    stored = await world.repo.list_for_project(world.project_id)
    assert {r.id for r in stored} == {first.id, other.id}
    assert await _count(world.engine, "signing_route_participants") == 6


async def test__scenario_transaction_rolled_back__nothing_stored(world: World) -> None:
    route = make_route(world.project_id)

    async def scenario() -> None:
        async with world.uow.begin():
            await world.repo.add(route, events=[make_event(route)])
            raise RuntimeError("уведомление не записалось")

    with pytest.raises(RuntimeError):
        await scenario()

    assert await world.repo.get(world.project_id, route.id) is None
    assert await world.repo.list_events(route.id) == []


# --- хранение ---


async def test__users__stored_as_users_id_and_join_with_users(world: World) -> None:
    route = make_full_route(world.project_id)
    signer = route.participants[1]
    assert signer.user_id is not None
    await seed_user(world.sessions, signer.user_id.hex)
    await world.repo.add(route, events=[make_event(route, actor_id=signer.user_id)])

    async with world.engine.connect() as conn:
        names = (
            await conn.execute(
                text(
                    "SELECT u.name FROM signing_route_participants p JOIN users u ON u.id = p.user_id"
                    " WHERE p.route_id = :route"
                ),
                {"route": route.id},
            )
        ).scalars()
        created_by = (
            await conn.execute(text("SELECT created_by FROM signing_routes WHERE id = :id"), {"id": route.id})
        ).scalar_one()
        actor = (await conn.execute(text("SELECT actor_id FROM signing_route_events"))).scalar_one()

    assert list(names) == [f"user {signer.user_id.hex[:6]}"]
    assert created_by == route.created_by.hex
    assert actor == signer.user_id.hex


async def test__project_deleted__routes_with_parts_and_history_deleted(world: World) -> None:
    route = make_full_route(world.project_id)
    stored = await world.repo.add(route, events=[make_event(route)])
    await world.repo.save(stored, events=[make_event(route, EventKind.approved)])

    async with world.engine.begin() as conn:
        await conn.execute(text("DELETE FROM projects WHERE id = :id"), {"id": world.project_id})

    for table in sorted(_TABLES):
        assert await _count(world.engine, table) == 0, table


async def test__save__archived_route__releases_documents_in_index(world: World) -> None:
    route = await world.repo.add(make_route(world.project_id, status=RouteStatus.completed))

    await world.repo.save(replace(route, status=RouteStatus.archived))

    async with world.engine.connect() as conn:
        active = (await conn.execute(text("SELECT bool_or(active) FROM signing_route_docs"))).scalar_one()
    assert active is False


async def test__get__unknown_route_with_lock__none(world: World) -> None:
    async with world.uow.begin():
        assert await world.repo.get(world.project_id, uuid4(), lock=True) is None
        assert await world.repo.get_open(world.project_id, "topic-approval", lock=True) is None
