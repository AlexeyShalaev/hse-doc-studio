"""ИИ-провайдеры сервера: личные у пользователя, общие у установки."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base


class AIProviderRow(Base):
    """Личный провайдер исчезает вместе с пользователем; у общего провайдера установки владельца нет."""

    __tablename__ = "ai_providers"
    __table_args__ = (
        CheckConstraint(
            "(owner_kind = 'user' AND owner_id IS NOT NULL) OR (owner_kind = 'instance' AND owner_id IS NULL)",
            name="ck_ai_providers_owner",
        ),
        Index("ix_ai_providers_owner", "owner_kind", "owner_id", "created_at"),
        CheckConstraint(
            "(type = 'runner') = (runner_id IS NOT NULL AND runner_endpoint IS NOT NULL)", name="ck_ai_providers_runner"
        ),
        CheckConstraint("type <> 'runner' OR owner_kind = 'user'", name="ck_ai_providers_runner_owner"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="user")
    owner_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    # Шифртекст ключа; привязка `column_aad("ai_providers", "api_key_enc", id)`. У локального Ollama ключа нет.
    api_key_enc: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    models: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    ssl_verify: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    connect_timeout_s: Mapped[float] = mapped_column(Float, nullable=False, server_default="10")
    request_timeout_s: Mapped[float] = mapped_column(Float, nullable=False, server_default="60")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Провайдер «через мой раннер»: раннер-ретранслятор и имя объявленного им ИИ-адреса.
    runner_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("runners.id", ondelete="CASCADE"))
    runner_endpoint: Mapped[str | None] = mapped_column(String(32))


encrypted_columns.register(EncryptedColumn("ai_providers", "api_key_enc", pk="id"))
