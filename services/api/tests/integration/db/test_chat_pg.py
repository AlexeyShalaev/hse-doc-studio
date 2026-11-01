"""PostgresChatRepository: личные чаты, атомарный seq, изоляция авторов, каскады, восстановление ходов."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.entities import (
    AgentRunRecord,
    ChatContentBlock,
    ChatMessage,
    ChatSession,
    ChatSummaryBlock,
    TokenUsage,
)
from hse_doc_studio.core.enums import AgentRunStatus, ChatContentKind, ChatMessageRole
from hse_doc_studio.core.projects.volume import UnsafePathError
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.chat import ChatMessageRow, ChatSessionRow
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.repositories.chat import PostgresChatRepository
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.contract.test_identity_contract import make_user
from tests.factories import make_project
from tests.fixtures.actors import as_actor

pytestmark = pytest.mark.pg

_ANNA = Actor.user("anna", name="Анна")
_BORIS = Actor.user("boris", name="Борис")
_T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


@dataclass
class World:
    sessions: SessionProvider
    volume: LocalDiskProjectVolume
    projects: JsonProjectRepository
    locator: PostgresProjectLocator
    repo: PostgresChatRepository

    async def add_project(self) -> Path:
        project_id = uuid4()
        folder = self.volume.allocate(project_id)
        self.projects.save(replace(make_project(folder=folder), id=project_id))
        with as_actor(_ANNA):
            await self.locator.register(folder)
        return folder

    async def count(self, row: type[ChatSessionRow] | type[ChatMessageRow]) -> int:
        async with self.sessions.use() as session:
            return (await session.execute(select(func.count()).select_from(row))).scalar_one()


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    await users.add(make_user("anna"))
    await users.add(make_user("boris"))
    volume = LocalDiskProjectVolume(tmp_path / "projects")
    projects = JsonProjectRepository()
    return World(
        sessions,
        volume,
        projects,
        PostgresProjectLocator(sessions, volume, projects),
        PostgresChatRepository(sessions, volume, tmp_path / "system-chats"),
    )


def make_session(folder: Path, **changes: object) -> ChatSession:
    session = ChatSession(id=uuid4(), project_folder=folder, title="Чат", doc_id=None, created_at=_T0, updated_at=_T0)
    return replace(session, **changes)


def make_message(session_id: UUID, text: str = "привет", *, minutes: int = 0, **changes: object) -> ChatMessage:
    message = ChatMessage(
        id=uuid4(),
        session_id=session_id,
        run_id=None,
        seq=-1,
        role=ChatMessageRole.user,
        blocks=[ChatContentBlock(kind=ChatContentKind.text, text=text)],
        created_at=_T0 + timedelta(minutes=minutes),
    )
    return replace(message, **changes)


def make_run(folder: Path, session_id: UUID, **changes: object) -> AgentRunRecord:
    run = AgentRunRecord(
        id=uuid4(),
        session_id=session_id,
        project_folder=folder,
        status=AgentRunStatus.running,
        created_at=_T0,
        started_at=_T0,
        finished_at=None,
        trigger_seq=0,
    )
    return replace(run, **changes)


async def test__session__round_trips_with_project_id(world: World) -> None:
    folder = await world.add_project()
    provider_id = uuid4()
    session = make_session(
        folder, doc_id="vkr", archived=True, default_provider_id=provider_id, default_model="m", persona="custom"
    )
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        loaded = await world.repo.get_session(folder, session.id)
    assert loaded == replace(session, project_id=world.volume.id_of(folder))


async def test__append_message__20_parallel_appends__seq_has_no_gaps(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        seqs = await asyncio.gather(
            *(world.repo.append_message(folder, make_message(session.id, str(i))) for i in range(20))
        )
        messages = await world.repo.list_messages(folder, session.id)
        loaded = await world.repo.get_session(folder, session.id)
    assert sorted(seqs) == list(range(20))
    assert [m.seq for m in messages] == list(range(20))
    assert loaded is not None
    assert loaded.message_count == 20


async def test__save_session__does_not_roll_back_message_counter(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        await world.repo.append_message(folder, make_message(session.id))
        await world.repo.save_session(replace(session, title="Новое имя"))
        loaded = await world.repo.get_session(folder, session.id)
        seq = await world.repo.append_message(folder, make_message(session.id))
    assert loaded is not None
    assert (loaded.title, loaded.message_count) == ("Новое имя", 1)
    assert seq == 1


async def test__append_message__bumps_updated_at_and_keeps_blocks_usage(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    call = ChatContentBlock(kind=ChatContentKind.tool_call, call_id="c1", tool_name="read_file", args={"path": "a.tex"})
    message = make_message(
        session.id, minutes=5, blocks=[call], usage=TokenUsage(input_tokens=3, output_tokens=4), model="m"
    )
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        await world.repo.append_message(folder, message)
        [loaded] = await world.repo.list_messages(folder, session.id)
        stored = await world.repo.get_session(folder, session.id)
    assert loaded == replace(message, seq=0)
    assert stored is not None
    assert stored.updated_at == message.created_at


async def test__append_message__unknown_session__value_error(world: World) -> None:
    folder = await world.add_project()
    with as_actor(_ANNA), pytest.raises(ValueError, match="not found"):
        await world.repo.append_message(folder, make_message(uuid4()))


async def test__chats__visible_only_to_author(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        await world.repo.append_message(folder, make_message(session.id))
        await world.repo.append_summary(
            folder,
            ChatSummaryBlock(
                id=uuid4(), session_id=session.id, covers_from_seq=0, covers_to_seq=0, created_at=_T0, text="s"
            ),
        )
        run = make_run(folder, session.id)
        await world.repo.save_run(run)

    with as_actor(_BORIS):
        assert await world.repo.list_sessions(folder) == []
        assert await world.repo.get_session(folder, session.id) is None
        assert await world.repo.list_messages(folder, session.id) == []
        assert await world.repo.list_summaries(folder, session.id) == []
        assert await world.repo.get_run(folder, run.id) is None
        assert await world.repo.list_runs(folder, session.id) == []
        assert await world.repo.list_all_run_ids(folder) == []
        assert await world.repo.delete_session(folder, session.id) is False
        with pytest.raises(ValueError, match="not found"):
            await world.repo.append_message(folder, make_message(session.id))
        with pytest.raises(ValueError, match="not found"):
            await world.repo.save_session(replace(session, title="Захват"))
        with pytest.raises(ValueError, match="not found"):
            await world.repo.save_run(replace(run, status=AgentRunStatus.interrupted))
        assert await world.repo.mark_compacted(folder, session.id, 10) == 0
        stolen = replace(make_message(session.id, "подмена"), seq=0)
        await world.repo.update_message(folder, stolen)

    with as_actor(_ANNA):
        [message] = await world.repo.list_messages(folder, session.id)
        loaded = await world.repo.get_session(folder, session.id)
    assert message.blocks[0].text == "привет"
    assert loaded is not None
    assert (loaded.title, loaded.message_count) == ("Чат", 1)


async def test__chats__same_project_two_authors_do_not_mix(world: World) -> None:
    folder = await world.add_project()
    mine, theirs = make_session(folder, title="мой"), make_session(folder, title="чужой")
    with as_actor(_ANNA):
        await world.repo.save_session(mine)
    with as_actor(_BORIS):
        await world.repo.save_session(theirs)
        assert [s.title for s in await world.repo.list_sessions(folder)] == ["чужой"]
    with as_actor(_ANNA):
        assert [s.title for s in await world.repo.list_sessions(folder)] == ["мой"]


async def test__chats__are_isolated_between_projects(world: World) -> None:
    mine, other = await world.add_project(), await world.add_project()
    session = make_session(mine)
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        assert await world.repo.list_sessions(other) == []
        assert await world.repo.get_session(other, session.id) is None


async def test__chats__without_actor__rejected(world: World) -> None:
    from hse_doc_studio.core.access.context import ActorRequired

    folder = await world.add_project()
    with as_actor(None), pytest.raises(ActorRequired):
        await world.repo.list_sessions(folder)
    with as_actor(Actor.local()), pytest.raises(ActorRequired):
        await world.repo.list_sessions(folder)


async def test__chats__folder_outside_volume__rejected(world: World, tmp_path: Path) -> None:
    with as_actor(_ANNA), pytest.raises(UnsafePathError):
        await world.repo.list_sessions(tmp_path / str(uuid4()))


async def test__mark_compacted__marks_up_to_seq_once(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        for i in range(4):
            await world.repo.append_message(folder, make_message(session.id, str(i)))
        assert await world.repo.mark_compacted(folder, session.id, 1) == 2
        assert await world.repo.mark_compacted(folder, session.id, 2) == 1
        flags = [m.compacted for m in await world.repo.list_messages(folder, session.id)]
    assert flags == [True, True, True, False]


async def test__update_message__replaces_content_keeps_seq(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    message = make_message(session.id)
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        seq = await world.repo.append_message(folder, message)
        await world.repo.update_message(folder, replace(message, seq=seq, compacted=True))
        [loaded] = await world.repo.list_messages(folder, session.id)
    assert (loaded.seq, loaded.compacted) == (0, True)


async def test__summaries__in_creation_order(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)

    def summary(minutes: int, text: str) -> ChatSummaryBlock:
        return ChatSummaryBlock(
            id=uuid4(),
            session_id=session.id,
            covers_from_seq=minutes,
            covers_to_seq=minutes + 1,
            created_at=_T0 + timedelta(minutes=minutes),
            text=text,
            model="m",
            token_estimate=7,
        )

    late, early = summary(5, "второй"), summary(1, "первый")
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        await world.repo.append_summary(folder, late)
        await world.repo.append_summary(folder, early)
        assert await world.repo.list_summaries(folder, session.id) == [early, late]


async def test__runs__save_update_list_and_recovery_scan_without_actor(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    run = make_run(
        folder, session.id, diagnostics=[{"stop": "end_turn"}], usage=TokenUsage(input_tokens=1, output_tokens=2)
    )
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        await world.repo.save_run(run)
        await world.repo.save_run(replace(run, iterations=3))
        assert [r.iterations for r in await world.repo.list_runs(folder, session.id)] == [3]

    with as_actor(None):
        assert await world.repo.list_all_run_ids(folder) == [run.id]
        stale = await world.repo.get_run(folder, run.id)
        assert stale is not None
        await world.repo.save_run(replace(stale, status=AgentRunStatus.interrupted, error="restart"))

    with as_actor(_ANNA):
        loaded = await world.repo.get_run(folder, run.id)
    assert loaded is not None
    assert (loaded.status, loaded.error, loaded.diagnostics) == (
        AgentRunStatus.interrupted,
        "restart",
        [{"stop": "end_turn"}],
    )


async def test__delete_session__removes_its_messages_summaries_and_runs(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        await world.repo.append_message(folder, make_message(session.id))
        await world.repo.save_run(make_run(folder, session.id))
        assert await world.repo.delete_session(folder, session.id) is True
        assert await world.repo.delete_session(folder, session.id) is False
        assert await world.repo.list_all_run_ids(folder) == []
    assert await world.count(ChatMessageRow) == 0


async def test__project_removed_from_catalog__chats_cascade(world: World) -> None:
    folder = await world.add_project()
    session = make_session(folder)
    with as_actor(_ANNA):
        await world.repo.save_session(session)
        await world.repo.append_message(folder, make_message(session.id))
    async with world.sessions.use() as db:
        await db.delete(await db.get(ProjectRow, world.volume.id_of(folder)))
    assert (await world.count(ChatSessionRow), await world.count(ChatMessageRow)) == (0, 0)


async def test__system_chats__are_separate_from_project_chats_and_private(world: World, tmp_path: Path) -> None:
    folder = await world.add_project()
    system_folder = tmp_path / "system-chats"
    project_id = world.volume.id_of(folder)
    bound = make_session(system_folder, project_id=project_id)
    free = make_session(system_folder)
    inside = make_session(folder)
    with as_actor(_ANNA):
        for session in (bound, free, inside):
            await world.repo.save_session(session)
        await world.repo.append_message(system_folder, make_message(bound.id))
        assert {s.id for s in await world.repo.list_sessions(system_folder)} == {bound.id, free.id}
        assert [s.id for s in await world.repo.list_sessions(folder)] == [inside.id]
        assert await world.repo.get_session(folder, bound.id) is None
        assert await world.repo.get_session(system_folder, inside.id) is None
        assert [m.seq for m in await world.repo.list_messages(system_folder, bound.id)] == [0]
    with as_actor(_BORIS):
        assert await world.repo.list_sessions(system_folder) == []

    async with world.sessions.use() as db:
        await db.delete(await db.get(ProjectRow, project_id))
    with as_actor(_ANNA):
        assert [s.id for s in await world.repo.list_sessions(system_folder)] == [free.id]
