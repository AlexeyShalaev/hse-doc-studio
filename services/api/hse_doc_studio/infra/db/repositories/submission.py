"""Записи сдачи в Postgres: журнал пакетов проекта, id проекта берётся из его папки на томе."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.entities import PackSubmissionRecord
from hse_doc_studio.core.projects.volume import IProjectVolume
from hse_doc_studio.infra.db.orm.submission import SubmissionRow
from hse_doc_studio.infra.db.session import SessionProvider
from hse_doc_studio.infra.persistence.serializers import (
    deserialize_pack_submission_record,
    serialize_pack_submission_record,
)


class PostgresPackSubmissionRepository:
    """IPackSubmissionRepository сервера: запись принадлежит проекту, автор фиксируется снимком при создании."""

    def __init__(self, sessions: SessionProvider, volume: IProjectVolume) -> None:
        self._sessions = sessions
        self._volume = volume

    async def list_for_project(self, project_folder: Path) -> list[PackSubmissionRecord]:
        project_id = self._volume.id_of(project_folder)
        stmt = (
            select(SubmissionRow)
            .where(SubmissionRow.project_id == project_id)
            .order_by(SubmissionRow.created_at, SubmissionRow.id)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_record(row, project_folder) for row in rows]

    async def get(self, project_folder: Path, submission_id: UUID) -> PackSubmissionRecord | None:
        project_id = self._volume.id_of(project_folder)
        async with self._sessions.use() as session:
            row = (
                await session.execute(
                    select(SubmissionRow).where(
                        SubmissionRow.id == submission_id, SubmissionRow.project_id == project_id
                    )
                )
            ).scalar_one_or_none()
        return None if row is None else _to_record(row, project_folder)

    async def save(self, record: PackSubmissionRecord) -> None:
        project_id = self._volume.id_of(record.project_folder)
        data = serialize_pack_submission_record(record)
        values: dict[str, Any] = {
            "profile_id": record.profile_id,
            "created_at": record.created_at,
            "archive_format": record.archive_format,
            "artifact_key": record.artifact_key,
            "output_path": data["output_path"],
            "data": {"doc_items": data["doc_items"], "extra_items": data["extra_items"]},
        }
        actor = current_actor()
        author: dict[str, Any] = {}
        if actor is not None and actor.kind is ActorKind.user and actor.id is not None:
            author = {"actor_id": actor.id, "actor_name": actor.name}
        async with self._sessions.use() as session:
            stmt = pg_insert(SubmissionRow).values(id=record.id, project_id=project_id, **values, **author)
            await session.execute(stmt.on_conflict_do_update(index_elements=[SubmissionRow.id], set_=values))


def _to_record(row: SubmissionRow, project_folder: Path) -> PackSubmissionRecord:
    return deserialize_pack_submission_record(
        {
            "id": str(row.id),
            "profile_id": row.profile_id,
            "created_at": row.created_at.isoformat(),
            "doc_items": row.data.get("doc_items", []),
            "extra_items": row.data.get("extra_items", []),
            "output_path": row.output_path,
            "output_dir": None,
            "archive_format": row.archive_format,
            "artifact_key": row.artifact_key,
        },
        project_folder=project_folder,
    )
