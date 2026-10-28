"""Список проектов и сценарии с id проекта в теле запроса на сервере: чужого проекта нет ни в списке, ни в чате."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.enums import EngineType, Lang, ProjectKind, ProjectStaffing
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.value_objects import Author
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.di.containers.api import create_container
from hse_doc_studio.use_cases.chat.system_chat import SystemCreateChatSessionUC
from hse_doc_studio.use_cases.projects.create_project import CreateProjectInput, CreateProjectUC
from hse_doc_studio.use_cases.projects.get_project_suggestions import GetProjectSuggestionsUC
from hse_doc_studio.use_cases.projects.list_projects import ListProjectsUC
from sqlalchemy import text

from tests.contract.test_identity_contract import make_user
from tests.fixtures.actors import as_actor

if TYPE_CHECKING:
    from dishka import AsyncContainer
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

ALICE = Actor.user("user-a")
BOB = Actor.user("user-b")


@dataclass
class World:
    container: AsyncContainer
    sessions: SessionProvider

    async def create(self, actor: Actor, name: str, authors: list[Author] | None = None) -> UUID:
        inp = CreateProjectInput(
            folder=None,
            pack_id="hse-cs-se",
            template_id="vkr",
            version="2026.1",
            name=name,
            kind=ProjectKind.research,
            staffing=ProjectStaffing.solo,
            lang=Lang.ru,
            engine=EngineType.xelatex,
            authors=authors or [],
            supervisor=None,
            co_supervisor=None,
            meta={},
        )
        async with self.container() as request:
            with as_actor(actor):
                return (await (await request.get(CreateProjectUC)).execute(inp)).project.id

    async def add_member(self, project_id: UUID, actor: Actor, role: str) -> None:
        async with self.sessions.use() as session:
            session.add(
                ProjectMemberRow(project_id=project_id, principal_kind="user", principal_id=actor.id, role=role)
            )

    async def listed(self, actor: Actor) -> list[UUID]:
        async with self.container() as request:
            with as_actor(actor):
                return [p.id for p in (await (await request.get(ListProjectsUC)).execute()).projects]


@pytest_asyncio.fixture
async def world(
    pg_migrated_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[World]:
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings.server, "projects_root", tmp_path / "projects")
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    await users.add(make_user("user-a"))
    await users.add(make_user("user-b"))
    container = create_container(StudioMode.server, engine=pg_migrated_engine)
    try:
        yield World(container, sessions)
    finally:
        await container.close()


async def test__list__each_user_sees_only_own_projects(world: World) -> None:
    mine = await world.create(ALICE, "Алисина")
    theirs = await world.create(BOB, "Бобова")

    assert await world.listed(ALICE) == [mine]
    assert await world.listed(BOB) == [theirs]


async def test__list__summary_carries_owner_and_my_role(world: World) -> None:
    project_id = await world.create(ALICE, "Алисина")
    await world.add_member(project_id, BOB, "reviewer")

    async with world.container() as request:
        uc = await request.get(ListProjectsUC)
        with as_actor(ALICE):
            own = (await uc.execute()).memberships[project_id]
        with as_actor(BOB):
            shared = (await uc.execute()).memberships[project_id]

    assert (own.my_role, own.owner.kind, own.owner.id, own.owner.name) == (Role.owner, "user", "user-a", "User-A")
    assert (shared.my_role, shared.owner.name) == (Role.reviewer, "User-A")


async def test__list__deleted_project__not_listed_for_member(world: World) -> None:
    project_id = await world.create(ALICE, "Алисина")
    await world.add_member(project_id, BOB, "reader")

    assert await world.listed(BOB) == [project_id]
    async with world.sessions.use() as session:
        await session.execute(text("UPDATE projects SET deleted_at = now()"))

    assert await world.listed(BOB) == []


async def test__suggestions__authors_and_folders_come_only_from_visible_projects(world: World) -> None:
    await world.create(ALICE, "Алисина", [Author(name="Секретный Автор", group="БПИ")])
    await world.create(BOB, "Бобова", [Author(name="Боб Авторов", group="БПИ")])

    async with world.container() as request:
        uc = await request.get(GetProjectSuggestionsUC)
        with as_actor(BOB):
            result = await uc.execute()

    assert [a.name for a in result.authors] == ["Боб Авторов"]
    assert result.folder_roots == []


async def test__checker__stranger_gets_not_found_and_weak_role_gets_forbidden(world: World) -> None:
    project_id = await world.create(ALICE, "Алисина")
    await world.add_member(project_id, BOB, "reader")

    async with world.container() as request:
        checker = await request.get(IProjectAccessChecker)
        with as_actor(ALICE):
            await checker.require(project_id, Action.AGENT_USE)
        with as_actor(BOB), pytest.raises(ProjectForbiddenError):
            await checker.require(project_id, Action.AGENT_USE)
        with as_actor(Actor.user("nobody")), pytest.raises(NotFoundError):
            await checker.require(project_id, Action.PROJECT_VIEW)
        with as_actor(ALICE), pytest.raises(NotFoundError):
            await checker.require(uuid4(), Action.PROJECT_VIEW)


async def test__system_chat__foreign_project_id_in_body__not_found_and_nothing_saved(world: World) -> None:
    project_id = await world.create(ALICE, "Алисина")

    async with world.container() as request:
        uc = await request.get(SystemCreateChatSessionUC)
        with as_actor(BOB), pytest.raises(NotFoundError):
            await uc.execute(project_id=project_id)
        with as_actor(ALICE):
            created = await uc.execute(project_id=project_id)

    assert created.session.project_id == project_id
