"""Итоги облачных сборок документов проекта: последняя удачная и состояние новой, без лога и проверок."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from hse_doc_studio.core.builds.entities import BuildStamp, DocumentCloudState
from hse_doc_studio.core.enums import CompileStatus
from hse_doc_studio.infra.db.orm.compile import CompileRecordRow
from hse_doc_studio.infra.db.session import SessionProvider

_COLUMNS = (
    CompileRecordRow.id,
    CompileRecordRow.doc_id,
    CompileRecordRow.finished_at,
    CompileRecordRow.pages,
    CompileRecordRow.source_commit,
    CompileRecordRow.output_sha256,
    CompileRecordRow.output_size,
    CompileRecordRow.actor_name,
)


class PostgresBuildStampRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def states(self, project_id: UUID) -> list[DocumentCloudState]:
        ok = (
            select(*_COLUMNS)
            .where(
                CompileRecordRow.project_id == project_id,
                CompileRecordRow.status == CompileStatus.success.value,
                CompileRecordRow.finished_at.is_not(None),
            )
            .distinct(CompileRecordRow.doc_id)
            .order_by(CompileRecordRow.doc_id, CompileRecordRow.finished_at.desc())
        )
        running = select(CompileRecordRow.doc_id).where(
            CompileRecordRow.project_id == project_id,
            CompileRecordRow.status.in_([CompileStatus.pending.value, CompileStatus.running.value]),
        )
        failed = (
            select(CompileRecordRow.doc_id, func.max(CompileRecordRow.finished_at))
            .where(CompileRecordRow.project_id == project_id, CompileRecordRow.status == CompileStatus.failure.value)
            .group_by(CompileRecordRow.doc_id)
        )
        async with self._sessions.use() as session:
            ok_rows = (await session.execute(ok)).all()
            running_docs = {row[0] for row in (await session.execute(running)).all()}
            failed_at = {row[0]: row[1] for row in (await session.execute(failed)).all()}
        stamps = {row.doc_id: _stamp(row) for row in ok_rows}
        docs = sorted(set(stamps) | running_docs | set(failed_at))
        return [
            DocumentCloudState(
                doc_id=doc,
                last_ok=stamps.get(doc),
                running=doc in running_docs,
                last_failed_at=failed_at.get(doc),
            )
            for doc in docs
        ]

    async def last_ok(self, project_id: UUID, doc_id: str) -> BuildStamp | None:
        stmt = (
            select(*_COLUMNS)
            .where(
                CompileRecordRow.project_id == project_id,
                CompileRecordRow.doc_id == doc_id,
                CompileRecordRow.status == CompileStatus.success.value,
                CompileRecordRow.finished_at.is_not(None),
            )
            .order_by(CompileRecordRow.finished_at.desc())
            .limit(1)
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).first()
        return None if row is None else _stamp(row)


def _stamp(row: Any) -> BuildStamp:
    return BuildStamp(
        compile_id=row.id,
        doc_id=row.doc_id,
        finished_at=row.finished_at,
        pages=row.pages,
        source_commit=row.source_commit,
        sha256=row.output_sha256,
        size=row.output_size,
        actor_name=row.actor_name,
    )
