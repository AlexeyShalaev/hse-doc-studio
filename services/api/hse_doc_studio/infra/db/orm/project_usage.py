"""Учёт места проекта: последнее измерение и инкременты записей."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class ProjectUsageRow(Base):
    __tablename__ = "project_usage"
    __table_args__ = (Index("ix_project_usage_measured_at", "measured_at"),)

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    bytes_tree: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    bytes_git: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    bytes_s3: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    measured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
