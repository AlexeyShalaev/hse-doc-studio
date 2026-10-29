"""Таблицы организаций, их участников и групп."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class OrgRow(Base):
    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Содержимое политик появится в этапе 3; сейчас внутри только версия формата.
    policies: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default=text("""'{"version": 1}'::jsonb"""))
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class OrgMemberRow(Base):
    __tablename__ = "org_members"
    __table_args__ = (
        CheckConstraint("role IN ('member', 'admin', 'owner')", name="org_member_role"),
        Index("ix_org_members_user_id", "user_id"),
    )

    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GroupRow(Base):
    __tablename__ = "groups"
    __table_args__ = (Index("ux_groups_org_name_lower", "org_id", text("lower(name)"), unique=True),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    # Под синхронизацию групп из SSO; пока не используется.
    external_ref: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GroupMemberRow(Base):
    __tablename__ = "group_members"
    __table_args__ = (Index("ix_group_members_user_id", "user_id"),)

    group_id: Mapped[str] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
