"""Уборка хвостов задач: выходы в S3 без владельца и устаревшие терминальные записи с логами.

Выходы лежат в `artifacts/<проект>/jobs/<задача>/` и маркеры в `announce/<проект>/<задача>/`. Их стирают коммит,
провал и применение результата, но раннер мог загрузить и умереть, а задачу снять по таймауту или отмене: префикс
тогда живёт, пока жив проект, и считается в квоту. Префикс старше порога удаляется, если записи задачи нет или она
терминальна (успешная и ещё не применённая ждёт довершения при старте). Строки применённых терминальных задач
и их файлы логов стираются по сроку хранения; 0 выключает стирание строк.
"""

from __future__ import annotations

import asyncio
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import delete, select

from hse_doc_studio.core.jobs.enums import JobState
from hse_doc_studio.core.storage import IObjectStore
from hse_doc_studio.infra.db.orm.jobs import JobRow
from hse_doc_studio.infra.db.session import SessionProvider

logger = structlog.get_logger()

_ARTIFACTS = "artifacts/"
_ANNOUNCE = "announce/"
_TERMINAL = tuple(s.value for s in JobState if s.is_terminal)
BATCH_SIZE = 500


@dataclass
class JobRetentionReport:
    output_prefixes: list[UUID] = field(default_factory=list)
    rows: int = 0


def _canonical_uuid(name: str) -> UUID | None:
    try:
        parsed = UUID(name)
    except ValueError:
        return None
    return parsed if str(parsed) == name else None


def _job_of(key: str) -> UUID | None:
    parts = key.split("/")
    if parts[0] == "artifacts" and len(parts) > 4 and parts[2] == "jobs":
        return _canonical_uuid(parts[3])
    if parts[0] == "announce" and len(parts) > 3:
        return _canonical_uuid(parts[2])
    return None


class JobRetention:
    def __init__(
        self,
        sessions: SessionProvider,
        store: IObjectStore,
        storage_root: Path,
        *,
        output_min_age: timedelta,
        retention: timedelta | None,
    ) -> None:
        self._sessions = sessions
        self._store = store
        self._logs = storage_root / "logs"
        self._output_min_age = output_min_age
        self._retention = retention

    async def run(self, now: datetime | None = None) -> JobRetentionReport:
        moment = now or datetime.now(tz=timezone.utc)
        report = JobRetentionReport()
        await self._sweep_outputs(moment - self._output_min_age, report)
        if self._retention is not None:
            await self._sweep_rows(moment - self._retention, report)
        if report.output_prefixes or report.rows:
            logger.info("job retention", output_prefixes=len(report.output_prefixes), rows=report.rows)
        return report

    async def _sweep_outputs(self, cutoff: datetime, report: JobRetentionReport) -> None:
        keys: dict[UUID, list[str]] = {}
        newest: dict[UUID, datetime] = {}
        for prefix in (_ARTIFACTS, _ANNOUNCE):
            for obj in await self._store.list_objects(prefix):
                job_id = _job_of(obj.key)
                if job_id is None:
                    continue
                keys.setdefault(job_id, []).append(obj.key)
                newest[job_id] = max(newest.get(job_id, obj.last_modified), obj.last_modified)
        for job_id, job_keys in keys.items():
            if newest[job_id] >= cutoff or await self._is_live(job_id):
                continue
            for key in job_keys:
                await self._store.delete(key)
            report.output_prefixes.append(job_id)

    async def _is_live(self, job_id: UUID) -> bool:
        """Выходы ещё нужны: задача идёт или её успех не применён."""
        async with self._sessions.use() as session:
            row = (await session.execute(select(JobRow.state, JobRow.applied_at).where(JobRow.id == job_id))).first()
        if row is None:
            return False
        state, applied_at = row
        if not JobState(state).is_terminal:
            return True
        return state == JobState.succeeded.value and applied_at is None

    async def _sweep_rows(self, cutoff: datetime, report: JobRetentionReport) -> None:
        while True:
            async with self._sessions.use() as session:
                ids = list(
                    (
                        await session.execute(
                            select(JobRow.id)
                            .where(JobRow.state.in_(_TERMINAL), JobRow.applied_at < cutoff)
                            .order_by(JobRow.applied_at)
                            .limit(BATCH_SIZE)
                        )
                    ).scalars()
                )
                if not ids:
                    return
                await session.execute(delete(JobRow).where(JobRow.id.in_(ids)))
            for job_id in ids:
                await asyncio.to_thread(shutil.rmtree, self._logs / str(job_id), ignore_errors=True)
            report.rows += len(ids)
            if len(ids) < BATCH_SIZE:
                return
