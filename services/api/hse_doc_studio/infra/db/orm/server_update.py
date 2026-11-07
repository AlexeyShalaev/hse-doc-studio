"""Запуски автообновления серверной установки."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class UpdateRunRow(Base):
    __tablename__ = "update_runs"
    __table_args__ = (
        CheckConstraint("kind IN ('update', 'rollback', 'downgrade')", name="kind"),
        CheckConstraint("trigger IN ('auto', 'manual')", name="trigger"),
        CheckConstraint(
            "status IN ('waiting_backup', 'queued', 'running', 'succeeded', 'rolled_back', 'failed', 'cancelled')",
            name="status",
        ),
        Index("ix_update_runs_created", text("created_at DESC")),
        # Не больше одного активного запуска: проверка атомарна на уровне базы.
        Index(
            "uq_update_runs_single_active",
            text("(true)"),
            unique=True,
            postgresql_where=text("status IN ('waiting_backup', 'queued', 'running')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str | None] = mapped_column(String(32))
    from_version: Mapped[str] = mapped_column(String(64), nullable=False)
    to_version: Mapped[str] = mapped_column(String(64), nullable=False)
    from_revision: Mapped[str | None] = mapped_column(String(64))
    to_revision: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    backup_run_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("backup_runs.id", ondelete="SET NULL"))
    restore_db: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    db_restored: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    digests_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    verify: Mapped[str] = mapped_column(String(16), nullable=False, server_default="digest")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default="[]")
