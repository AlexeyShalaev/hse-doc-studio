"""Идентичности подписи сервера: метаданные у владельца, закрытый ключ шифртекстом и только по разрешению админа."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base


class SigningIdentityRow(Base):
    """Идентичность исчезает вместе с пользователем."""

    __tablename__ = "signing_identities"
    __table_args__ = (Index("ix_signing_identities_owner", "owner_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_cn: Mapped[str] = mapped_column(Text, nullable=False)
    not_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trusted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    fingerprint: Mapped[str | None] = mapped_column(Text)
    protected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Открытая часть: хранится без шифрования.
    cert_pem: Mapped[str | None] = mapped_column(Text)
    # Шифртекст закрытого ключа; привязка `column_aad("signing_identities", "key_enc", id)`.
    key_enc: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


encrypted_columns.register(EncryptedColumn("signing_identities", "key_enc", pk="id"))
