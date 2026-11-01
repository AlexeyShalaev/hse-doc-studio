"""Postgres: последнее состояние проверок самодиагностики."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.diagnostics.entities import CheckResult, DiagStatus
from hse_doc_studio.core.diagnostics.state import CheckState
from hse_doc_studio.infra.db.orm.diagnostics import DiagCheckRow
from hse_doc_studio.infra.db.session import SessionProvider


class SqlDiagStore:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def load(self) -> dict[str, CheckState]:
        async with self._sessions.use() as db:
            rows = (await db.execute(select(DiagCheckRow))).scalars().all()
        return {
            r.check_id: CheckState(
                result=CheckResult(
                    r.check_id, DiagStatus(r.status), r.reason, dict(r.values), r.checked_at, r.duration_ms
                ),
                status_since=r.status_since,
                streak=r.streak,
                notified_status=DiagStatus(r.notified_status) if r.notified_status is not None else None,
                notified_at=r.notified_at,
            )
            for r in rows
        }

    async def save(self, state: CheckState) -> None:
        res = state.result
        data = {
            "status": int(res.status),
            "reason": res.reason,
            "values": dict(res.values),
            "checked_at": res.checked_at,
            "duration_ms": res.duration_ms,
            "status_since": state.status_since,
            "streak": state.streak,
            "notified_status": int(state.notified_status) if state.notified_status is not None else None,
            "notified_at": state.notified_at,
        }
        stmt = pg_insert(DiagCheckRow).values(check_id=res.check_id, **data)
        stmt = stmt.on_conflict_do_update(index_elements=[DiagCheckRow.check_id], set_=data)
        async with self._sessions.use() as db:
            await db.execute(stmt)
