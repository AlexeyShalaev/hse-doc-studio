"""Сборка мусора сирот: папки тома и объекты S3 проектов, которых нет в таблице projects.

Строка с deleted_at проектом ещё считается (её стирает purge). Свежие находки не трогаем: папка выделяется
раньше строки каталога. Удаляется только то, что лежит прямо в корне тома под каноническим UUID, и только
через том, поэтому за пределы projects_root GC не выходит.
"""

from __future__ import annotations

import asyncio
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import select

from hse_doc_studio.core.projects.volume import IProjectVolume, UnsafePathError
from hse_doc_studio.core.storage import IObjectStore
from hse_doc_studio.infra.db.orm.projects import ProjectRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.projects.usage_meter import project_objects_prefix

logger = structlog.get_logger()

ARTIFACTS_PREFIX = "artifacts/"


@dataclass
class OrphanReport:
    folders: list[UUID] = field(default_factory=list)
    prefixes: list[UUID] = field(default_factory=list)


def _canonical_uuid(name: str) -> UUID | None:
    try:
        parsed = UUID(name)
    except ValueError:
        return None
    return parsed if str(parsed) == name else None


class OrphanGc:
    def __init__(
        self, sessions: SessionProvider, volume: IProjectVolume, store: IObjectStore, min_age: timedelta
    ) -> None:
        self._sessions = sessions
        self._volume = volume
        self._store = store
        self._min_age = min_age

    async def run(self, now: datetime | None = None) -> OrphanReport:
        report = OrphanReport()
        cutoff = (now or datetime.now(tz=timezone.utc)) - self._min_age
        await self._folders(cutoff, report)
        await self._prefixes(cutoff, report)
        if report.folders or report.prefixes:
            logger.info("orphan gc", folders=len(report.folders), prefixes=len(report.prefixes))
        return report

    async def _has_row(self, project_id: UUID) -> bool:
        async with self._sessions.use() as session:
            found = await session.execute(select(ProjectRow.id).where(ProjectRow.id == project_id))
            return found.scalar_one_or_none() is not None

    def _candidate_folders(self, cutoff: datetime) -> list[UUID]:
        root = self._volume.root
        if not root.is_dir():
            return []
        found: list[UUID] = []
        with os.scandir(root) as it:
            for entry in it:
                project_id = _canonical_uuid(entry.name)
                if project_id is None or entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    continue
                if datetime.fromtimestamp(entry.stat(follow_symlinks=False).st_mtime, tz=timezone.utc) < cutoff:
                    found.append(project_id)
        return found

    async def _folders(self, cutoff: datetime, report: OrphanReport) -> None:
        for project_id in await asyncio.to_thread(self._candidate_folders, cutoff):
            if await self._has_row(project_id):
                continue
            try:
                await asyncio.to_thread(self._volume.remove, project_id)
            except (OSError, UnsafePathError) as exc:
                logger.warning("orphan gc: folder not removed", project_id=str(project_id), exc=str(exc))
                continue
            report.folders.append(project_id)

    async def _prefixes(self, cutoff: datetime, report: OrphanReport) -> None:
        by_project: dict[UUID, list[str]] = defaultdict(list)
        newest: dict[UUID, datetime] = {}
        for obj in await self._store.list_objects(ARTIFACTS_PREFIX):
            parts = obj.key.split("/")
            project_id = _canonical_uuid(parts[1]) if len(parts) > 2 else None
            if project_id is None:
                continue
            by_project[project_id].append(obj.key)
            newest[project_id] = max(newest.get(project_id, obj.last_modified), obj.last_modified)
        for project_id, keys in by_project.items():
            if newest[project_id] >= cutoff or await self._has_row(project_id):
                continue
            for key in keys:
                await self._store.delete(key)
            report.prefixes.append(project_id)
            logger.info("orphan gc: prefix removed", prefix=project_objects_prefix(project_id), objects=len(keys))
