"""Стирание удалённых проектов по сроку: папка на томе, затем строка каталога.

Папка определяется только по id строки (``projects_root/<uuid>``), а не по ``workspace_path``: испорченное
значение в БД не может направить стирание за пределы тома. Свежеудалённые проекты и проекты с неудачно
стёртой папкой остаются в каталоге, следующий проход повторит попытку.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import delete, select

from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider

logger = structlog.get_logger()

BATCH_SIZE = 50


@dataclass
class PurgeReport:
    purged: list[UUID] = field(default_factory=list)
    failed: list[UUID] = field(default_factory=list)


class ProjectPurger:
    def __init__(
        self, sessions: SessionProvider, volume: IProjectVolume, retention: timedelta, *, batch_size: int = BATCH_SIZE
    ) -> None:
        self._sessions = sessions
        self._volume = volume
        self._retention = retention
        self._batch_size = batch_size

    async def purge_expired(self, now: datetime | None = None) -> PurgeReport:
        """Стирает проекты, удалённые раньше ``now - retention``; нулевой срок значит «не стирать никогда»."""
        report = PurgeReport()
        if self._retention <= timedelta(0):
            return report
        cutoff = (now or datetime.now(tz=timezone.utc)) - self._retention
        stmt = (
            select(ProjectRow.id)
            .where(ProjectRow.deleted_at.is_not(None), ProjectRow.deleted_at <= cutoff)
            .order_by(ProjectRow.deleted_at)
            .limit(self._batch_size)
            .with_for_update(skip_locked=True)
        )
        async with self._sessions.begin():
            async with self._sessions.use() as session:
                ids = list((await session.execute(stmt)).scalars().all())
            for project_id in ids:
                if await self._purge_one(project_id, cutoff):
                    report.purged.append(project_id)
                else:
                    report.failed.append(project_id)
        if report.purged or report.failed:
            logger.info("projects purged", purged=len(report.purged), failed=len(report.failed))
        return report

    async def _purge_one(self, project_id: UUID, cutoff: datetime) -> bool:
        try:
            await asyncio.to_thread(self._remove_folder, project_id)
        except Exception as exc:  # noqa: BLE001 — одна неудача не должна останавливать остальные
            logger.exception("project purge: folder not removed", project_id=str(project_id), exc=str(exc))
            return False
        # Условие на deleted_at повторено: строку, возвращённую из корзины между выборкой и стиранием, не трогаем.
        gone = delete(ProjectRow).where(
            ProjectRow.id == project_id, ProjectRow.deleted_at.is_not(None), ProjectRow.deleted_at <= cutoff
        )
        async with self._sessions.use() as session:
            await session.execute(gone)
        return True

    def _remove_folder(self, project_id: UUID) -> None:
        try:
            self._volume.remove(project_id)
        except FileNotFoundError:
            return
