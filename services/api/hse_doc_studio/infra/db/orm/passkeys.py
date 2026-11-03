"""Ключи входа по passkey (WebAuthn): открытый ключ, счётчик подписей и домен, к которому ключ привязан."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class PasskeyRow(Base):
    __tablename__ = "passkeys"
    __table_args__ = (Index("ix_passkeys_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # base64url: по спецификации до 1023 байт.
    credential_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sign_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    rp_id: Mapped[str] = mapped_column(String(253), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    transports: Mapped[list[str]] = mapped_column(ARRAY(String(32)), nullable=False, server_default="{}")
    aaguid: Mapped[str] = mapped_column(String(36), nullable=False, server_default="")
    backup_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    backed_up: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
