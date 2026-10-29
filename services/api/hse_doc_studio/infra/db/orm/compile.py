"""Таблица записей сборок: история сборок документов проекта на сервере."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid, desc, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class CompileRecordRow(Base):
    __tablename__ = "compile_records"
    __table_args__ = (
        Index("ix_compile_records_project_doc_started", "project_id", "doc_id", desc("started_at")),
        Index(
            "ix_compile_records_unfinished",
            "project_id",
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    doc_id: Mapped[str] = mapped_column(String(256), nullable=False)
    engine: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    # Кто запустил: id остаётся ссылкой, имя снимком, чтобы запись пережила удаление пользователя.
    actor_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    actor_name: Mapped[str | None] = mapped_column(String(256))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pages: Mapped[int | None] = mapped_column(Integer)
    words: Mapped[int | None] = mapped_column(Integer)
    chars: Mapped[int | None] = mapped_column(Integer)
    check_results: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    log: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Путь к PDF относительно папки проекта; абсолютные пути томов в БД не попадают.
    output_path: Mapped[str | None] = mapped_column(Text)
