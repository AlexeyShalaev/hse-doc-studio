"""Таблицы трека invites: приглашения в проект, запросы доступа, передачи владения и уведомления."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base

_GRANT_ROLES = "('reader', 'reviewer', 'editor')"
NOTIFICATION_KINDS = (
    "project_invitation",
    "invitation_accepted",
    "invitation_declined",
    "access_request",
    "access_request_decided",
    "transfer_request",
    "transfer_decided",
    "member_removed",
)


class ProjectInvitationRow(Base):
    __tablename__ = "project_invitations"
    __table_args__ = (
        CheckConstraint("invitee_user_id IS NOT NULL OR invitee_email IS NOT NULL", name="invitee"),
        CheckConstraint(f"role IN {_GRANT_ROLES}", name="role"),
        CheckConstraint("status IN ('pending', 'accepted', 'declined', 'revoked')", name="status"),
        Index(
            "ux_project_invitations_pending_user",
            "project_id",
            "invitee_user_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND invitee_user_id IS NOT NULL"),
        ),
        Index(
            "ux_project_invitations_pending_email",
            "project_id",
            "invitee_email",
            unique=True,
            postgresql_where=text("status = 'pending' AND invitee_email IS NOT NULL"),
        ),
        Index(
            "ix_project_invitations_email_pending",
            "invitee_email",
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_project_invitations_project_created", "project_id", text("created_at DESC")),
        Index("ix_project_invitations_invitee_user_id", "invitee_user_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    invitee_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Нормализованная почта (NFKC, нижний регистр).
    invitee_email: Mapped[str | None] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    persona: Mapped[str | None] = mapped_column(String(64))
    can_share: Mapped[bool] = mapped_column(Boolean, nullable=False)
    show_sources: Mapped[bool] = mapped_column(Boolean, nullable=False)
    can_edit_all: Mapped[bool] = mapped_column(Boolean, nullable=False)
    message: Mapped[str | None] = mapped_column(String(1000))
    # Хеш секрета ссылки из письма; у приглашения существующему человеку его нет.
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    invited_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # `expired` не хранится: это `pending` с истёкшим сроком.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    registration_invite_id: Mapped[str | None] = mapped_column(String(64))


class AccessRequestRow(Base):
    __tablename__ = "access_requests"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'denied', 'cancelled')", name="status"),
        CheckConstraint("(status = 'approved') = (granted_role IS NOT NULL)", name="granted"),
        Index(
            "ux_access_requests_pending",
            "project_id",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("ix_access_requests_user_created", "user_id", text("created_at DESC")),
        Index("ix_access_requests_project_created", "project_id", text("created_at DESC")),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(64))
    granted_role: Mapped[str | None] = mapped_column(String(16))


class ProjectTransferRow(Base):
    __tablename__ = "project_transfers"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'accepted', 'declined', 'cancelled', 'superseded')", name="status"),
        CheckConstraint("from_kind IN ('user', 'org') AND to_kind IN ('user', 'org')", name="kinds"),
        Index("ux_project_transfers_pending", "project_id", unique=True, postgresql_where=text("status = 'pending'")),
        Index("ix_project_transfers_to_pending", "to_kind", "to_id", postgresql_where=text("status = 'pending'")),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    from_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    from_id: Mapped[str] = mapped_column(String(64), nullable=False)
    to_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    to_id: Mapped[str] = mapped_column(String(64), nullable=False)
    initiated_by: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(String(64))


class NotificationRow(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(f"kind IN {NOTIFICATION_KINDS!r}", name="kind"),
        Index("ix_notifications_user_created", "user_id", text("created_at DESC")),
        Index("ix_notifications_user_unread", "user_id", postgresql_where=text("read_at IS NULL")),
        Index(
            "ux_notifications_dedupe",
            "user_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
        Index("ix_notifications_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # Только id и подписи на момент события, без секретов.
    payload: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dedupe_key: Mapped[str | None] = mapped_column(String(128))
