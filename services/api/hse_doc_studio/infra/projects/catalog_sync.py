"""Копия name/kind/lang проекта в таблице projects и сверка каталога с томом.

Источник правды о содержимом проекта остаётся project.json. Таблица держит копию для списков и
админки: её обновляет декоратор над репозиторием проектов на каждый save, а на старте сверка
исправляет то, что декоратор не успел или что оператор поменял руками.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import func, select, update

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.projects.volume import IProjectVolume, UnsafePathError
from hse_doc_studio.core.repositories import IProjectRepository
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

logger = structlog.get_logger()


class ProjectCatalogMirror:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def mirror(self, project_id: UUID, project: Project) -> bool:
        """Переносит name/kind/lang в строку каталога; False, если строки нет или копия уже совпадает."""
        stmt = (
            update(ProjectRow)
            .where(
                ProjectRow.id == project_id,
                (ProjectRow.name != project.name)
                | (ProjectRow.kind != project.kind.value)
                | (ProjectRow.lang != project.lang.value),
            )
            .values(name=project.name, kind=project.kind.value, lang=project.lang.value, updated_at=func.now())
            .returning(ProjectRow.id)
        )
        async with self._sessions.use() as session:
            return (await session.execute(stmt)).scalar_one_or_none() is not None


class MirroringProjectRepository:
    """Декоратор над IProjectRepository: после save копия уходит в каталог.

    Порт пока синхронный, поэтому запись в БД ставится задачей в текущий цикл и не блокирует save.
    Если цикла нет или запись не удалась, копию исправит сверка на старте.
    """

    def __init__(self, inner: IProjectRepository, volume: IProjectVolume, mirror: ProjectCatalogMirror) -> None:
        self._inner = inner
        self._volume = volume
        self._mirror = mirror
        self._pending: set[asyncio.Task[bool]] = set()

    def get(self, folder: Path) -> Project | None:
        return self._inner.get(folder)

    def save(self, project: Project) -> None:
        self._inner.save(project)
        try:
            project_id = self._volume.id_of(project.folder)
        except UnsafePathError:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.debug("project mirror: нет цикла, копию исправит сверка", project_id=str(project_id))
            return
        task = loop.create_task(self._mirror.mirror(project_id, project))
        self._pending.add(task)
        task.add_done_callback(self._done)

    async def drain(self) -> None:
        """Дожидается отправленных копий: для остановки сервера и тестов."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    def _done(self, task: asyncio.Task[bool]) -> None:
        self._pending.discard(task)
        if not task.cancelled() and task.exception() is not None:
            logger.warning("project mirror: copy failed", exc=str(task.exception()))


@dataclass
class ReconcileReport:
    checked: int = 0
    missing: list[UUID] = field(default_factory=list)
    restored: list[UUID] = field(default_factory=list)
    refreshed: list[UUID] = field(default_factory=list)


class ProjectCatalogReconciler:
    """Сверка при старте: помечает проекты без папки и подтягивает копию из project.json. Приложение не роняет."""

    def __init__(self, sessions: SessionProvider, volume: IProjectVolume, projects: IProjectRepository) -> None:
        self._sessions = sessions
        self._volume = volume
        self._projects = projects
        self._mirror = ProjectCatalogMirror(sessions)

    async def reconcile(self) -> ReconcileReport:
        report = ReconcileReport()
        stmt = select(ProjectRow.id, ProjectRow.volume_missing_at).where(ProjectRow.deleted_at.is_(None))
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).all()
        for project_id, missing_at in rows:
            report.checked += 1
            try:
                await self._check(project_id, missing_at is not None, report)
            except Exception as exc:  # noqa: BLE001 — одна битая строка не должна останавливать сверку
                logger.warning("project reconcile: error", project_id=str(project_id), exc=str(exc))
        if report.missing:
            logger.warning("project reconcile: volume folders missing", count=len(report.missing))
        return report

    async def _check(self, project_id: UUID, was_missing: bool, report: ReconcileReport) -> None:
        if not self._volume.exists(project_id):
            if not was_missing:
                await self._set_missing(project_id, missing=True)
            report.missing.append(project_id)
            return
        if was_missing:
            await self._set_missing(project_id, missing=False)
            report.restored.append(project_id)
        project = self._projects.get(self._volume.path_of(project_id))
        if project is not None and await self._mirror.mirror(project_id, project):
            report.refreshed.append(project_id)

    async def _set_missing(self, project_id: UUID, *, missing: bool) -> None:
        stmt = (
            update(ProjectRow)
            .where(ProjectRow.id == project_id)
            .values(volume_missing_at=func.now() if missing else None)
        )
        async with self._sessions.use() as session:
            await session.execute(stmt)
