"""Артефакты проекта, выгруженные локальной Студией: запись в БД, сами байты в объектном хранилище."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, desc
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class ProjectArtifactRow(Base):
    __tablename__ = "project_artifacts"
    __table_args__ = (Index("ix_project_artifacts_project_doc_uploaded", "project_id", "doc_id", desc("uploaded_at")),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    doc_id: Mapped[str] = mapped_column(String(128), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    pages: Mapped[int | None] = mapped_column(Integer)
    source_commit: Mapped[str | None] = mapped_column(String(64))
    built_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Автор остаётся ссылкой, имя снимком: запись переживает удаление пользователя.
    uploaded_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    uploaded_by_name: Mapped[str | None] = mapped_column(String(256))
    client_name: Mapped[str | None] = mapped_column(String(128))
