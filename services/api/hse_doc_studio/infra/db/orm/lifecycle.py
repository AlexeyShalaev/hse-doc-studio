"""Статистика последней очистки по источникам жизненного цикла данных и прогоны «Освободить место»."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class LifecycleRunRow(Base):
    __tablename__ = "lifecycle_runs"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_removed: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    runs: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    total_removed: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class LifecycleSweepRow(Base):
    """Прогон «Освободить место» (storage-cleanup.md, 5.4): хранятся 20 последних, идущий не больше одного."""

    __tablename__ = "lifecycle_sweeps"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'cancelling', 'done', 'cancelled', 'error', 'interrupted')", name="status"
        ),
        Index("ix_lifecycle_sweeps_started", text("started_at DESC")),
        # Не больше одного идущего прогона: проверка атомарна на уровне базы, второй запуск получает 409.
        Index(
            "uq_lifecycle_sweeps_active",
            text("(true)"),
            unique=True,
            postgresql_where=text("status IN ('running', 'cancelling')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    steps: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
