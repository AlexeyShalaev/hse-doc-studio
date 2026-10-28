"""Каталог проектов сервера в Postgres: поиск папки по id и видимость по членству."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import Select, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.context import ActorRequired, require_actor
from hse_doc_studio.core.access.entities import Actor, ActorKind, Role
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ProjectStaffing
from hse_doc_studio.core.projects.locator import ProjectAlreadyRegisteredError
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.core.repositories import IProjectRepository
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

logger = structlog.get_logger()

USER_PRINCIPAL = "user"


class PostgresProjectLocator:
    """Папка проекта это projects_root/<id>; БД отвечает, какие проекты есть и кому они видны."""

    def __init__(self, sessions: SessionProvider, volume: IProjectVolume, projects: IProjectRepository) -> None:
        self._sessions = sessions
        self._volume = volume
        self._projects = projects

    async def folder_of(self, project_id: UUID) -> Path | None:
        workspace = await self._workspace_of(project_id)
        if workspace is None:
            return None
        return self._volume.resolve_workspace(workspace)

    async def locate(self, project_id: UUID) -> tuple[Path, Project] | None:
        folder = await self.folder_of(project_id)
        if folder is None:
            return None
        try:
            project = self._projects.get(folder)
        except Exception as exc:  # noqa: BLE001 — битый или пропавший project.json не должен ронять запрос
            logger.warning("project locator: error loading project", project_id=str(project_id), exc=str(exc))
            return None
        return (folder, project) if project is not None else None

    async def list_visible(self, actor: Actor | None) -> list[Path]:
        if actor is None:
            raise ActorRequired("список проектов без актора")
        if actor.kind is not ActorKind.user or actor.id is None:
            return []
        member = (
            select(ProjectMemberRow.project_id)
            .where(
                ProjectMemberRow.project_id == ProjectRow.id,
                ProjectMemberRow.principal_kind == USER_PRINCIPAL,
                ProjectMemberRow.principal_id == actor.id,
            )
            .exists()
        )
        stmt = (
            select(ProjectRow.workspace_path)
            .where(ProjectRow.deleted_at.is_(None), or_(ProjectRow.owner_user_id == actor.id, member))
            .order_by(ProjectRow.created_at, ProjectRow.id)
        )
        return await self._folders(stmt)

    async def list_all(self) -> list[Path]:
        stmt = (
            select(ProjectRow.workspace_path)
            .where(ProjectRow.deleted_at.is_(None))
            .order_by(ProjectRow.created_at, ProjectRow.id)
        )
        return await self._folders(stmt)

    async def register(self, folder: Path) -> None:
        """Заводит строку каталога и владельца для готовой папки; владелец это текущий актор."""
        actor = require_actor()
        if actor.kind is not ActorKind.user or actor.id is None:
            raise ActorRequired("владельцем проекта может быть только пользователь")
        project_id = self._volume.id_of(folder)
        project = self._projects.get(folder)
        if project is None:
            raise FileNotFoundError(f"в {folder.name} нет project.json")
        values = {
            "id": project_id,
            "name": project.name,
            "owner_user_id": actor.id,
            "workspace_path": str(project_id),
            "kind": project.kind.value,
            "lang": project.lang.value,
            # Единственный момент, когда права берутся из файла: проект создаёт его владелец.
            "team": project.staffing is ProjectStaffing.team,
            "shared_enabled": project.shared_enabled,
        }
        insert = pg_insert(ProjectRow).values(**values)
        stmt = insert.on_conflict_do_update(
            index_elements=[ProjectRow.id],
            set_={
                "name": insert.excluded.name,
                "kind": insert.excluded.kind,
                "lang": insert.excluded.lang,
                "team": insert.excluded.team,
                "shared_enabled": insert.excluded.shared_enabled,
                "updated_at": func.now(),
                "deleted_at": None,
            },
            where=ProjectRow.owner_user_id == actor.id,
        ).returning(ProjectRow.id)
        async with self._sessions.use() as session:
            if (await session.execute(stmt)).scalar_one_or_none() is None:
                raise ProjectAlreadyRegisteredError(str(project_id))
            member = (
                pg_insert(ProjectMemberRow)
                .values(
                    project_id=project_id,
                    principal_kind=USER_PRINCIPAL,
                    principal_id=actor.id,
                    role=Role.owner.value,
                    can_share=True,
                    can_edit_all=True,
                )
                .on_conflict_do_nothing()
            )
            await session.execute(member)

    async def unregister(self, folder: Path) -> None:
        """Мягкое удаление: строка остаётся с deleted_at, физическая чистка тома отдельной задачей."""
        project_id = self._volume.id_of(folder)
        stmt = (
            update(ProjectRow)
            .where(ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        async with self._sessions.use() as session:
            await session.execute(stmt)

    async def _workspace_of(self, project_id: UUID) -> str | None:
        stmt = select(ProjectRow.workspace_path).where(ProjectRow.id == project_id, ProjectRow.deleted_at.is_(None))
        async with self._sessions.use() as session:
            return (await session.execute(stmt)).scalar_one_or_none()

    async def _folders(self, stmt: Select[Any]) -> list[Path]:
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [self._volume.resolve_workspace(workspace) for workspace in rows]
