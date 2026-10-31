"""Проверка прав на проект из тела запроса: решение берётся из policy.decide по членству актора."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.context import ActorRequired
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.infra.identity.project_access import LocalProjectAccessChecker, ServerProjectAccessChecker

from tests.fixtures.actors import as_actor

READER = Actor.user("reader")
EDITOR = Actor.user("editor")
STRANGER = Actor.user("stranger")


class FakeAcl:
    def __init__(self) -> None:
        self.asked: list[tuple[str | None, UUID]] = []

    async def load_for(self, actor: Actor, project_id: UUID, *, include_links: bool = True) -> ProjectAcl | None:
        self.asked.append((actor.id, project_id))
        role = {"reader": Role.reader, "editor": Role.editor}.get(actor.id or "")
        if role is None:
            return None
        return ProjectAcl(project_id=str(project_id), owner_id="owner", grants={actor.id or "": Grant(role=role)})

    async def set_shared_enabled(self, project_id: UUID, enabled: bool) -> None:
        raise AssertionError("не нужен")


async def test__server_checker__stranger__not_found() -> None:
    checker = ServerProjectAccessChecker(FakeAcl())

    with as_actor(STRANGER), pytest.raises(NotFoundError):
        await checker.require(uuid4(), Action.AGENT_USE)


async def test__server_checker__reader_lacks_role__forbidden() -> None:
    checker = ServerProjectAccessChecker(FakeAcl())

    with as_actor(READER), pytest.raises(ProjectForbiddenError):
        await checker.require(uuid4(), Action.AGENT_USE)


async def test__server_checker__editor__passes() -> None:
    checker = ServerProjectAccessChecker(FakeAcl())

    with as_actor(EDITOR):
        await checker.require(uuid4(), Action.AGENT_USE)


async def test__server_checker__local_actor__skips_repository() -> None:
    acl = FakeAcl()

    with as_actor(Actor.local()):
        await ServerProjectAccessChecker(acl).require(uuid4(), Action.AGENT_USE)

    assert acl.asked == []


async def test__server_checker__no_actor__refuses() -> None:
    with as_actor(None), pytest.raises(ActorRequired):
        await ServerProjectAccessChecker(FakeAcl()).require(uuid4(), Action.AGENT_USE)


async def test__local_checker__any_project__allows() -> None:
    with as_actor(Actor.local()):
        await LocalProjectAccessChecker().require(uuid4(), Action.PROJECT_SETTINGS)
