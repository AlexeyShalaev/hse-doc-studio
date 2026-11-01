"""Статистика последней очистки по источникам жизненного цикла данных."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
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
