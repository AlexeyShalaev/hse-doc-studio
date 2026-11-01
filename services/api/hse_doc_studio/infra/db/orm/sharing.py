"""Ссылки доступа к проекту, гостевые сессии, ссылочные права вошедших и агрегированные переходы."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base


class ShareLinkRow(Base):
    __tablename__ = "share_links"
    __table_args__ = (
        CheckConstraint("role IN ('reader', 'reviewer', 'editor')", name="role"),
        CheckConstraint("(revoked_at IS NULL) = (revoke_reason IS NULL)", name="revoke"),
        Index("ix_share_links_project_active", "project_id", postgresql_where=text("revoked_at IS NULL")),
        Index("ix_share_links_created_by", "created_by"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    show_sources: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    require_login: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    password_hash: Mapped[str | None] = mapped_column(Text)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # Привязка `column_aad("share_links", "token_enc", id)`: владелец копирует ссылку снова.
    token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(12), nullable=False)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by: Mapped[str | None] = mapped_column(String(64))
    revoke_reason: Mapped[str | None] = mapped_column(String(16))
    replaced_by: Mapped[str | None] = mapped_column(String(64))
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GuestSessionRow(Base):
    __tablename__ = "guest_sessions"
    __table_args__ = (Index("ix_guest_sessions_expires_at", "expires_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str] = mapped_column(String(512), nullable=False, server_default="")
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)


class GuestSessionLinkRow(Base):
    __tablename__ = "guest_session_links"
    __table_args__ = (Index("ux_guest_session_links_project", "session_id", "project_id", unique=True),)

    session_id: Mapped[str] = mapped_column(ForeignKey("guest_sessions.id", ondelete="CASCADE"), primary_key=True)
    link_id: Mapped[str] = mapped_column(ForeignKey("share_links.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShareLinkGrantRow(Base):
    __tablename__ = "share_link_grants"
    __table_args__ = (Index("ix_share_link_grants_user_project", "user_id", "project_id"),)

    link_id: Mapped[str] = mapped_column(ForeignKey("share_links.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ShareLinkVisitRow(Base):
    __tablename__ = "share_link_visits"
    __table_args__ = (
        CheckConstraint("visitor_kind IN ('guest', 'user')", name="visitor_kind"),
        Index("ix_share_link_visits_link_last", "link_id", text("last_at DESC")),
    )

    link_id: Mapped[str] = mapped_column(ForeignKey("share_links.id", ondelete="CASCADE"), primary_key=True)
    visitor_kind: Mapped[str] = mapped_column(String(8), primary_key=True)
    visitor_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    visitor_name: Mapped[str | None] = mapped_column(String(128))
    first_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    opens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_ip: Mapped[str | None] = mapped_column(String(64))


encrypted_columns.register(EncryptedColumn("share_links", "token_enc", pk="id"))
