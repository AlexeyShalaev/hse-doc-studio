"""Счётчики расхода по периодам и журнал вызовов ИИ-шлюза."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class UsageCounterRow(Base):
    """Расход владельца за период; новый период это новая строка, поэтому сброс не требует расписания."""

    __tablename__ = "usage_counters"
    __table_args__ = (Index("ix_usage_counters_period", "resource", "period_start"),)

    owner_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resource: Mapped[str] = mapped_column(String(32), primary_key=True)
    period_start: Mapped[date] = mapped_column(Date, primary_key=True)
    used: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AiUsageRow(Base):
    """Один вызов модели через шлюз: кто, куда, сколько токенов и чем кончилось. Тел запросов нет."""

    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_at", "at"),
        Index("ix_ai_usage_user_at", "user_id", "at"),
        Index("ix_ai_usage_provider_at", "provider_id", "at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64))
    org_id: Mapped[str | None] = mapped_column(String(64))
    project_id: Mapped[UUID | None] = mapped_column(Uuid)
    provider_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    provider_owner: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    outcome: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    counted: Mapped[bool] = mapped_column(nullable=False, server_default="false")
