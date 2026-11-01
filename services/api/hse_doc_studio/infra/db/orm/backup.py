"""Назначения и запуски бэкапов."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base


class BackupDestinationRow(Base):
    """Куда складывать бэкапы. Ключи доступа шифртекстом, привязка `column_aad("backup_destinations", колонка, id)`."""

    __tablename__ = "backup_destinations"
    __table_args__ = (
        CheckConstraint("kind IN ('s3', 'local')", name="kind"),
        Index("uq_backup_destinations_name", text("lower(name)"), unique=True),
        Index("uq_backup_destinations_default", "is_default", unique=True, postgresql_where=text("is_default")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    endpoint: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str] = mapped_column(String(64), nullable=False, server_default="us-east-1")
    bucket: Mapped[str | None] = mapped_column(String(256))
    prefix: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")
    path_style: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    local_path: Mapped[str | None] = mapped_column(Text)
    access_key_enc: Mapped[str | None] = mapped_column(Text)
    secret_key_enc: Mapped[str | None] = mapped_column(Text)
    access_key_hint: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_ok: Mapped[bool | None] = mapped_column(Boolean)
    last_check_error: Mapped[str | None] = mapped_column(Text)


class BackupRunRow(Base):
    __tablename__ = "backup_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running', 'ok', 'failed', 'interrupted')", name="status"),
        CheckConstraint("trigger IN ('manual', 'schedule')", name="trigger"),
        Index("ix_backup_runs_started", text("started_at DESC")),
        Index("ix_backup_runs_destination", "destination_id", text("started_at DESC")),
        # Не больше одного идущего запуска: проверка атомарна на уровне базы.
        Index("uq_backup_runs_single_running", "status", unique=True, postgresql_where=text("status = 'running'")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    destination_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("backup_destinations.id", ondelete="SET NULL"))
    destination_name: Mapped[str] = mapped_column(String(128), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    started_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    backup_id: Mapped[str | None] = mapped_column(String(64))
    error: Mapped[str | None] = mapped_column(Text)
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


encrypted_columns.register(EncryptedColumn("backup_destinations", "access_key_enc", pk="id"))
encrypted_columns.register(EncryptedColumn("backup_destinations", "secret_key_enc", pk="id"))
