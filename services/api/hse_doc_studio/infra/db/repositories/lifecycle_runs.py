"""Postgres: итог последней очистки по источникам жизненного цикла."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.lifecycle.ports import RunStat
from hse_doc_studio.infra.db.orm.lifecycle import LifecycleRunRow
from hse_doc_studio.infra.db.session import SessionProvider


class SqlLifecycleRuns:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def record(self, key: str, *, at: datetime, duration_ms: int, removed: int, error: str | None) -> None:
        insert = pg_insert(LifecycleRunRow).values(
            key=key,
            last_run_at=at,
            last_duration_ms=duration_ms,
            last_removed=removed,
            last_error=error,
            runs=1,
            total_removed=removed,
        )
        stmt = insert.on_conflict_do_update(
            index_elements=[LifecycleRunRow.key],
            set_={
                "last_run_at": at,
                "last_duration_ms": duration_ms,
                "last_removed": removed,
                "last_error": error,
                "runs": LifecycleRunRow.runs + 1,
                "total_removed": LifecycleRunRow.total_removed + removed,
            },
        )
        async with self._sessions.use() as db:
            await db.execute(stmt)

    async def all(self) -> dict[str, RunStat]:
        async with self._sessions.use() as db:
            rows = (await db.execute(select(LifecycleRunRow))).scalars().all()
        return {
            r.key: RunStat(
                key=r.key,
                last_run_at=r.last_run_at,
                last_duration_ms=r.last_duration_ms,
                last_removed=r.last_removed,
                last_error=r.last_error,
                runs=r.runs,
                total_removed=r.total_removed,
            )
            for r in rows
        }
