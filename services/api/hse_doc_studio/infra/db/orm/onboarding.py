"""Состояние онбординга пользователя: одна строка на человека."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class UserOnboardingRow(Base):
    __tablename__ = "user_onboarding"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'suggested', 'in_progress', 'completed', 'skipped')", name="status"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    scenario_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    step: Mapped[str | None] = mapped_column(String(64))
    answers: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
