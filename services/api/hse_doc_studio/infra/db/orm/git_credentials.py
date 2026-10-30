"""Git-доступы пользователей и привязки доступа к удалённому репозиторию проекта."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base


class GitCredentialRow(Base):
    """Токен или ключ ssh. Исчезает вместе с владельцем."""

    __tablename__ = "git_credentials"
    __table_args__ = (Index("ix_git_credentials_owner", "owner_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int | None] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    token_family: Mapped[str | None] = mapped_column(Text)
    public_key: Mapped[str | None] = mapped_column(Text)
    fingerprint_sha256: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Шифртекст токена или закрытого ключа; привязка `column_aad("git_credentials", "secret_enc", id)`.
    secret_enc: Mapped[str] = mapped_column(Text, nullable=False)


class GitRemoteBindingRow(Base):
    """У проекта один удалённый репозиторий, поэтому и одна привязка. Исчезает с проектом и с доступом."""

    __tablename__ = "git_remote_bindings"
    __table_args__ = (Index("ix_git_remote_bindings_credential", "credential_id"),)

    project_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    credential_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("git_credentials.id", ondelete="CASCADE"), nullable=False
    )
    bound_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    # Схема, хост и порт адреса, для которых владелец разрешил доступ участникам проекта.
    scheme: Mapped[str] = mapped_column(String(8), nullable=False)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


encrypted_columns.register(EncryptedColumn("git_credentials", "secret_enc", pk="id"))
