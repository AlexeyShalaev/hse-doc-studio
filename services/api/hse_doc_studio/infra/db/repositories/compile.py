"""Записи сборок в Postgres: история документа проекта, id проекта берётся из его папки на томе."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.entities import CompileRecord
from hse_doc_studio.core.enums import CompileStatus
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.infra.db.orm.compile import CompileRecordRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.serializers import deserialize_compile_record, serialize_compile_record

DEFAULT_RECORDS_PER_DOCUMENT = 50
DEFAULT_LOG_LIMIT_BYTES = 1024 * 1024
_TRUNCATED_MARK = "[... начало лога обрезано: превышен предел размера ...]\n"
_UNFINISHED = (CompileStatus.pending, CompileStatus.running)


class PostgresCompileRepository:
    """ICompileRepository сервера.

    Запись принадлежит проекту, а не пользователю: историю видят все, у кого есть доступ к проекту
    (его проверяют выше). Автор запуска фиксируется снимком при создании записи. Фоновая задача
    без актора (завершение сборки, восстановление после сбоя) снимок не трогает.
    """

    def __init__(
        self,
        sessions: SessionProvider,
        volume: IProjectVolume,
        *,
        keep_per_document: int = DEFAULT_RECORDS_PER_DOCUMENT,
        log_limit_bytes: int = DEFAULT_LOG_LIMIT_BYTES,
    ) -> None:
        self._sessions = sessions
        self._volume = volume
        self._keep = keep_per_document
        self._log_limit = log_limit_bytes

    async def get_for_project(self, project_folder: Path, compile_id: UUID) -> CompileRecord | None:
        project_id = self._volume.id_of(project_folder)
        async with self._sessions.use() as session:
            row = (
                await session.execute(
                    select(CompileRecordRow).where(
                        CompileRecordRow.id == compile_id, CompileRecordRow.project_id == project_id
                    )
                )
            ).scalar_one_or_none()
        return None if row is None else _to_record(row, project_folder)

    async def list_for_document(self, project_folder: Path, doc_id: str) -> list[CompileRecord]:
        project_id = self._volume.id_of(project_folder)
        stmt = (
            select(CompileRecordRow)
            .where(CompileRecordRow.project_id == project_id, CompileRecordRow.doc_id == doc_id)
            .order_by(CompileRecordRow.started_at, CompileRecordRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_record(row, project_folder) for row in rows]

    async def list_unfinished(self, project_folder: Path) -> list[CompileRecord]:
        project_id = self._volume.id_of(project_folder)
        stmt = (
            select(CompileRecordRow)
            .where(CompileRecordRow.project_id == project_id, CompileRecordRow.status.in_(_UNFINISHED))
            .order_by(CompileRecordRow.started_at, CompileRecordRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_record(row, project_folder) for row in rows]

    async def save(self, record: CompileRecord) -> None:
        project_id = self._volume.id_of(record.project_folder)
        data = serialize_compile_record(record)
        values: dict[str, Any] = {
            "doc_id": record.doc_id,
            "engine": str(record.engine),
            "status": str(record.status),
            "started_at": record.started_at,
            "finished_at": record.finished_at,
            "pages": record.pages,
            "words": record.words,
            "chars": record.chars,
            "check_results": data["check_results"],
            "log": _clip_log(record.log, self._log_limit),
            "output_path": data["output_path"],
        }
        actor = current_actor()
        author: dict[str, Any] = {}
        if actor is not None and actor.kind is ActorKind.user and actor.id is not None:
            author = {"actor_id": actor.id, "actor_name": actor.name}
        async with self._sessions.use() as session:
            stmt = pg_insert(CompileRecordRow).values(id=record.id, project_id=project_id, **values, **author)
            await session.execute(stmt.on_conflict_do_update(index_elements=[CompileRecordRow.id], set_=values))
            await self._trim(session, project_id, record.doc_id)

    async def _trim(self, session: Any, project_id: UUID, doc_id: str) -> None:
        """Оставляет последние N записей документа; незавершённые не удаляются."""
        newest = (
            select(CompileRecordRow.id)
            .where(CompileRecordRow.project_id == project_id, CompileRecordRow.doc_id == doc_id)
            .order_by(CompileRecordRow.started_at.desc(), CompileRecordRow.id.desc())
            .limit(self._keep)
        )
        await session.execute(
            delete(CompileRecordRow).where(
                CompileRecordRow.project_id == project_id,
                CompileRecordRow.doc_id == doc_id,
                CompileRecordRow.status.not_in(_UNFINISHED),
                CompileRecordRow.id.not_in(newest),
            )
        )


def _clip_log(log: str, limit_bytes: int) -> str:
    """Лог сверх предела теряет начало: итог сборки и ошибки находятся в конце."""
    raw = log.encode("utf-8")
    if len(raw) <= limit_bytes:
        return log
    room = max(limit_bytes - len(_TRUNCATED_MARK.encode("utf-8")), 0)
    tail = raw[len(raw) - room :].decode("utf-8", errors="ignore") if room else ""
    return _TRUNCATED_MARK + tail


def _to_record(row: CompileRecordRow, project_folder: Path) -> CompileRecord:
    return deserialize_compile_record(
        {
            "id": str(row.id),
            "doc_id": row.doc_id,
            "engine": row.engine,
            "status": row.status,
            "started_at": row.started_at.isoformat(),
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "log": row.log,
            "output_path": row.output_path,
            "check_results": row.check_results,
            "pages": row.pages,
            "words": row.words,
            "chars": row.chars,
        },
        project_folder=project_folder,
    )
