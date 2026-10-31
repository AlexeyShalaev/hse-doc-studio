"""Артефакты проекта в Postgres: журнал выгруженных PDF; байты лежат в объектном хранилище."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select

from hse_doc_studio.core.artifacts.entities import ArtifactKind, ProjectArtifact
from hse_doc_studio.infra.db.orm.artifacts import ProjectArtifactRow
from hse_doc_studio.infra.db.session import SessionProvider


class PostgresProjectArtifactRepository:
    def __init__(self, sessions: SessionProvider) -> None:
        self._sessions = sessions

    async def add(self, artifact: ProjectArtifact) -> None:
        async with self._sessions.use() as session:
            session.add(_to_row(artifact))

    async def get(self, project_id: UUID, artifact_id: UUID) -> ProjectArtifact | None:
        stmt = select(ProjectArtifactRow).where(
            ProjectArtifactRow.id == artifact_id, ProjectArtifactRow.project_id == project_id
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return None if row is None else _to_entity(row)

    async def latest(self, project_id: UUID, doc_id: str, kind: ArtifactKind) -> ProjectArtifact | None:
        stmt = (
            select(ProjectArtifactRow)
            .where(
                ProjectArtifactRow.project_id == project_id,
                ProjectArtifactRow.doc_id == doc_id,
                ProjectArtifactRow.kind == kind.value,
            )
            .order_by(ProjectArtifactRow.uploaded_at.desc(), ProjectArtifactRow.id)
            .limit(1)
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return None if row is None else _to_entity(row)

    async def list_for_project(self, project_id: UUID, *, doc_id: str | None = None) -> list[ProjectArtifact]:
        stmt = select(ProjectArtifactRow).where(ProjectArtifactRow.project_id == project_id)
        if doc_id is not None:
            stmt = stmt.where(ProjectArtifactRow.doc_id == doc_id)
        stmt = stmt.order_by(ProjectArtifactRow.uploaded_at.desc(), ProjectArtifactRow.id)
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_entity(row) for row in rows]

    async def delete(self, project_id: UUID, artifact_id: UUID) -> ProjectArtifact | None:
        stmt = (
            delete(ProjectArtifactRow)
            .where(ProjectArtifactRow.id == artifact_id, ProjectArtifactRow.project_id == project_id)
            .returning(ProjectArtifactRow)
        )
        async with self._sessions.use() as session:
            row = (await session.execute(stmt)).scalar_one_or_none()
        return None if row is None else _to_entity(row)

    async def prune(self, project_id: UUID, doc_id: str, kind: ArtifactKind, *, keep: int) -> list[ProjectArtifact]:
        newest = (
            select(ProjectArtifactRow.id)
            .where(
                ProjectArtifactRow.project_id == project_id,
                ProjectArtifactRow.doc_id == doc_id,
                ProjectArtifactRow.kind == kind.value,
            )
            .order_by(ProjectArtifactRow.uploaded_at.desc(), ProjectArtifactRow.id)
            .limit(keep)
        )
        stmt = (
            delete(ProjectArtifactRow)
            .where(
                ProjectArtifactRow.project_id == project_id,
                ProjectArtifactRow.doc_id == doc_id,
                ProjectArtifactRow.kind == kind.value,
                ProjectArtifactRow.id.not_in(newest),
            )
            .returning(ProjectArtifactRow)
        )
        async with self._sessions.use() as session:
            rows = (await session.execute(stmt)).scalars().all()
        return [_to_entity(row) for row in rows]


def _to_row(a: ProjectArtifact) -> ProjectArtifactRow:
    return ProjectArtifactRow(
        id=a.id,
        project_id=a.project_id,
        kind=a.kind.value,
        doc_id=a.doc_id,
        file_name=a.file_name,
        size=a.size,
        sha256=a.sha256,
        object_key=a.object_key,
        pages=a.pages,
        source_commit=a.source_commit,
        built_at=a.built_at,
        uploaded_at=a.uploaded_at,
        uploaded_by=a.uploaded_by,
        uploaded_by_name=a.uploaded_by_name,
        client_name=a.client_name,
    )


def _to_entity(row: ProjectArtifactRow) -> ProjectArtifact:
    return ProjectArtifact(
        id=row.id,
        project_id=row.project_id,
        kind=ArtifactKind(row.kind),
        doc_id=row.doc_id,
        file_name=row.file_name,
        size=row.size,
        sha256=row.sha256,
        object_key=row.object_key,
        pages=row.pages,
        source_commit=row.source_commit,
        built_at=row.built_at,
        uploaded_at=row.uploaded_at,
        uploaded_by=row.uploaded_by,
        uploaded_by_name=row.uploaded_by_name,
        client_name=row.client_name,
    )
