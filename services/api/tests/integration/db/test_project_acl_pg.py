"""Членство проекта из Postgres: роли, 404 и 403, а project.json права не задаёт."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from hse_doc_studio.api import guards
from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.policy import Decision, decide
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ProjectStaffing
from hse_doc_studio.infra.db.engine import create_sessionmaker
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow
from hse_doc_studio.infra.db.repositories.identity import SqlUserRepository
from hse_doc_studio.infra.db.repositories.project_acl import PostgresProjectAclRepository, RequestAclCache
from hse_doc_studio.infra.db.repositories.projects import PostgresProjectLocator
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.projects.acl_flags import AclFlagsCache
from hse_doc_studio.infra.projects.catalog_sync import (
    MirroringProjectRepository,
    ProjectCatalogMirror,
    ProjectCatalogReconciler,
)
from hse_doc_studio.infra.projects.volume import LocalDiskProjectVolume

from tests.contract.test_identity_contract import make_user
from tests.factories import make_project
from tests.fixtures.actors import as_actor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.pg

OWNER = Actor.user("user-a")
EDITOR = Actor.user("user-b")
STRANGER = Actor.user("user-c")


@dataclass
class World:
    sessions: SessionProvider
    volume: LocalDiskProjectVolume
    raw: JsonProjectRepository
    repo: MirroringProjectRepository
    locator: PostgresProjectLocator
    acl: PostgresProjectAclRepository
    flags: AclFlagsCache

    async def add(self, **fields: object) -> Project:
        project_id = uuid4()
        folder = self.volume.allocate(project_id)
        project = replace(make_project(folder=folder), id=project_id, **fields)
        self.raw.save(project)
        with as_actor(OWNER):
            await self.locator.register(folder)
        return project

    async def member(self, project_id: UUID, actor: Actor, role: str, **extra: object) -> None:
        assert actor.id is not None
        async with self.sessions.use() as session:
            session.add(
                ProjectMemberRow(
                    project_id=project_id, principal_kind="user", principal_id=actor.id, role=role, **extra
                )
            )


@pytest_asyncio.fixture
async def world(pg_migrated_engine: AsyncEngine, tmp_path: Path) -> World:
    sessions = SessionProvider(create_sessionmaker(pg_migrated_engine))
    users = SqlUserRepository(sessions)
    for name in ("user-a", "user-b", "user-c"):
        await users.add(make_user(name))
    volume = LocalDiskProjectVolume(tmp_path / "projects")
    raw = JsonProjectRepository()
    flags = AclFlagsCache()
    repo = MirroringProjectRepository(raw, volume, ProjectCatalogMirror(sessions), flags)
    return World(
        sessions, volume, raw, repo, PostgresProjectLocator(sessions, volume, repo),
        PostgresProjectAclRepository(sessions, flags), flags,
    )  # fmt: skip


async def test__load_for__owner__owner_grant(world: World) -> None:
    project = await world.add()

    acl = await world.acl.load_for(OWNER, project.id)

    assert acl is not None
    assert acl.owner_id == "user-a"
    grant = acl.grant_for(OWNER)
    assert grant is not None
    assert grant.role is Role.owner
    assert grant.can_share
    assert decide(OWNER, Action.PROJECT_DELETE, acl) is Decision.allow


async def test__load_for__direct_member__grant_fields_from_row(world: World) -> None:
    project = await world.add()
    await world.member(project.id, EDITOR, "editor", persona="ivanov", show_sources=False, can_edit_all=True)

    acl = await world.acl.load_for(EDITOR, project.id)

    assert acl is not None
    grant = acl.grant_for(EDITOR)
    assert grant is not None
    assert (grant.role, grant.persona_slug, grant.show_sources, grant.can_edit_all) == (
        Role.editor,
        "ivanov",
        False,
        True,
    )
    assert list(acl.grants) == ["user-b"]


async def test__load_for__not_a_member__none_means_404(world: World) -> None:
    project = await world.add()

    acl = await world.acl.load_for(STRANGER, project.id)

    assert acl is None
    assert decide(STRANGER, Action.PROJECT_VIEW, acl) is Decision.not_found


async def test__load_for__role_too_low__403(world: World) -> None:
    project = await world.add()
    await world.member(project.id, EDITOR, "reader")

    acl = await world.acl.load_for(EDITOR, project.id)

    assert decide(EDITOR, Action.PROJECT_VIEW, acl) is Decision.allow
    assert decide(EDITOR, Action.FILES_WRITE, acl) is Decision.forbidden


async def test__load_for__unknown_project_guest_and_garbage_role__none(world: World) -> None:
    project = await world.add()
    await world.member(project.id, EDITOR, "superuser")

    assert await world.acl.load_for(OWNER, uuid4()) is None
    assert await world.acl.load_for(Actor.guest("link-1"), project.id) is None
    assert await world.acl.load_for(Actor.local(), project.id) is None
    assert await world.acl.load_for(EDITOR, project.id) is None


async def test__load_for__soft_deleted_project__none(world: World) -> None:
    project = await world.add()
    with as_actor(OWNER):
        await world.locator.unregister(project.folder)

    assert await world.acl.load_for(OWNER, project.id) is None


async def test__load_for__team_and_shared_flags_from_db(world: World) -> None:
    project = await world.add(staffing=ProjectStaffing.team, shared_enabled=False)

    acl = await world.acl.load_for(OWNER, project.id)

    assert acl is not None
    assert (acl.team, acl.shared_enabled) == (True, False)


async def test__request_cache__repeated_asks__same_loaded_value(world: World) -> None:
    project = await world.add()
    cache = RequestAclCache(world.acl)

    first = await cache.load_for(OWNER, project.id)
    await world.member(project.id, EDITOR, "reader")
    second = await cache.load_for(OWNER, project.id)

    assert first is second


async def test__pulled_project_json__does_not_change_rights_or_flags(world: World) -> None:
    project = await world.add(staffing=ProjectStaffing.solo, shared_enabled=True)
    await world.member(project.id, EDITOR, "reader")
    # git pull принёс project.json, где ссылка на общий доступ и командный режим включены иначе
    world.raw.save(replace(project, staffing=ProjectStaffing.team, shared_enabled=False))

    acl = await world.acl.load_for(EDITOR, project.id)
    assert acl is not None
    assert (acl.team, acl.shared_enabled) == (False, True)
    grant = acl.grant_for(EDITOR)
    assert grant is not None
    assert grant.role is Role.reader
    assert await world.acl.load_for(STRANGER, project.id) is None

    seen = world.repo.get(project.folder)
    assert seen is not None
    assert (seen.staffing, seen.shared_enabled) == (ProjectStaffing.solo, True)


async def test__save_after_pull__file_overwritten_from_db(world: World) -> None:
    project = await world.add(staffing=ProjectStaffing.solo, shared_enabled=True)
    await world.acl.load_for(OWNER, project.id)
    world.raw.save(replace(project, staffing=ProjectStaffing.team, shared_enabled=False))

    loaded = world.repo.get(project.folder)
    assert loaded is not None
    world.repo.save(replace(loaded, name="Новое имя"))
    await world.repo.drain()

    on_disk = world.raw.get(project.folder)
    assert on_disk is not None
    assert (on_disk.staffing, on_disk.shared_enabled, on_disk.name) == (ProjectStaffing.solo, True, "Новое имя")


async def test__reconcile__polluted_file__rewritten_from_db(world: World) -> None:
    project = await world.add(shared_enabled=True)
    world.raw.save(replace(project, shared_enabled=False))

    report = await ProjectCatalogReconciler(world.sessions, world.volume, world.repo).reconcile()

    assert report.acl_rewritten == [project.id]
    on_disk = world.raw.get(project.folder)
    assert on_disk is not None
    assert on_disk.shared_enabled is True


async def test__set_shared_enabled__db_first_then_file_follows(world: World) -> None:
    project = await world.add(shared_enabled=True)
    cache = RequestAclCache(world.acl)
    assert (await cache.load_for(OWNER, project.id)) is not None

    await cache.set_shared_enabled(project.id, False)
    world.repo.save(replace(project, shared_enabled=False))

    acl = await cache.load_for(OWNER, project.id)
    assert acl is not None
    assert acl.shared_enabled is False
    on_disk = world.raw.get(project.folder)
    assert on_disk is not None
    assert on_disk.shared_enabled is False


class _Container:
    def __init__(self, repository: object) -> None:
        self._repository = repository

    async def get(self, _type: object) -> object:
        return self._repository


class _State:
    def __init__(self, container: object) -> None:
        self.dishka_container = container


class _Request:
    def __init__(self, container: object) -> None:
        self.state = _State(container)


async def test__guard_load_project_acl__delegates_to_repository(world: World) -> None:
    project = await world.add()
    request = _Request(_Container(RequestAclCache(world.acl)))
    set_current_actor(OWNER)

    acl = await guards.load_project_acl(request, str(project.id))  # type: ignore[arg-type]
    assert acl is not None
    assert acl.owner_id == "user-a"

    set_current_actor(STRANGER)
    assert await guards.load_project_acl(request, str(project.id)) is None  # type: ignore[arg-type]
    assert await guards.load_project_acl(request, "not-a-uuid") is None  # type: ignore[arg-type]
