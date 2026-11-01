"""Таблица записей сдачи: журнал пакетов проекта; сам архив лежит в объектном хранилище."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, desc
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class SubmissionRow(Base):
    __tablename__ = "submissions"
    __table_args__ = (Index("ix_submissions_project_created", "project_id", desc("created_at")),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(256), nullable=False)
    # Кто собрал пакет: id остаётся ссылкой, имя снимком, чтобы запись пережила удаление пользователя.
    actor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    actor_name: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archive_format: Mapped[str] = mapped_column(String(16), nullable=False, server_default="zip")
    artifact_key: Mapped[str | None] = mapped_column(Text)
    # Путь архива относительно папки проекта; абсолютные пути томов в БД не попадают.
    output_path: Mapped[str] = mapped_column(Text, nullable=False)
    # Состав пакета: doc_items и extra_items в форме serialize_pack_submission_record.
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
