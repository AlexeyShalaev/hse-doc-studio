"""Подключённые Студии: последний сигнал присутствия каждого устройства человека."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class ConnectedDeviceRow(Base):
    __tablename__ = "connected_devices"
    __table_args__ = (
        Index("ix_connected_devices_last_seen", "last_seen_at"),
        Index("ix_connected_devices_project_ids", "project_ids", postgresql_using="gin"),
    )

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    os: Mapped[str] = mapped_column(String(16), nullable=False)
    activity: Mapped[str] = mapped_column(String(16), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_id: Mapped[str | None] = mapped_column(String(64))
    # Раннер, объявленные модели и проекты: только метаданные состояния, без путей и содержимого.
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")
    project_ids: Mapped[list[str]] = mapped_column(ARRAY(String(36)), nullable=False, server_default="{}")
