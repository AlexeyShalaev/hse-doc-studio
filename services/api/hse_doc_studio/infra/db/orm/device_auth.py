"""Вход устройства в git сервера (device flow): код устройства хешем, секрет выданного токена шифртекстом до выдачи."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base


class DeviceAuthorizationRow(Base):
    __tablename__ = "device_authorizations"
    __table_args__ = (
        Index("ix_device_authorizations_expires_at", "expires_at"),
        CheckConstraint("status IN ('pending', 'approved', 'denied', 'delivered')", name="status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    device_code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    user_code: Mapped[str] = mapped_column(String(9), nullable=False, unique=True)
    client_name: Mapped[str] = mapped_column(String(128), nullable=False)
    client_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_scopes: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False)
    granted_scopes: Mapped[list[str] | None] = mapped_column(ARRAY(String(32)))
    client_ip: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64))
    token_id: Mapped[str | None] = mapped_column(String(64))
    # Привязка `column_aad("device_authorizations", "token_secret_enc", id)`; стирается при выдаче устройству.
    token_secret_enc: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


encrypted_columns.register(EncryptedColumn("device_authorizations", "token_secret_enc", pk="id"))
