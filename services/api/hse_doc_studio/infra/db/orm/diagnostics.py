"""Последний результат каждой проверки самодиагностики."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class DiagCheckRow(Base):
    __tablename__ = "diag_checks"
    __table_args__ = (CheckConstraint("status IN (0, 1, 2)", name="status"),)

    check_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    values: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    streak: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    notified_status: Mapped[int | None] = mapped_column(SmallInteger)
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
