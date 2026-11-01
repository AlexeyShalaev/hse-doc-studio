"""Ревью-комментарии: треды на фрагмент файла и комментарии в них."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class ReviewThreadRow(Base):
    __tablename__ = "review_threads"
    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved')", name="status"),
        Index("ix_review_threads_project_path", "project_id", "path"),
        Index("ix_review_threads_project_activity", "project_id", text("updated_at DESC")),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    # Цитата с контекстом и подсказкой смещений (core.review.entities.Anchor).
    anchor: Mapped[Any] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    # Автор: id человека или гостевой сессии (`gs_…`), поэтому без внешнего ключа; имя на момент события.
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_by: Mapped[str | None] = mapped_column(String(64))
    resolved_by_name: Mapped[str | None] = mapped_column(String(256))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewCommentRow(Base):
    __tablename__ = "review_comments"
    __table_args__ = (Index("ix_review_comments_thread_created", "thread_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    thread_id: Mapped[str] = mapped_column(ForeignKey("review_threads.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[str | None] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(256), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
