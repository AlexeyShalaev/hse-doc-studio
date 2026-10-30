"""Таблицы проектов: каталог проектов сервера и участники."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class ProjectRow(Base):
    """Каталог проектов; источник правды о содержимом остаётся project.json, здесь копия name/kind/lang."""

    __tablename__ = "projects"
    __table_args__ = (
        Index("ix_projects_owner_user_id", "owner_user_id"),
        Index("ix_projects_owner_org_id", "owner_org_id"),
        CheckConstraint("build_runners IN ('shared', 'owner')", name="build_runners"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    # Организацию с проектами не удалить: сначала проекты передают или стирают окончательно.
    owner_org_id: Mapped[str | None] = mapped_column(ForeignKey("orgs.id", ondelete="RESTRICT"))
    workspace_path: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False)
    org_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    nda: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Права зависят от этих двух полей, поэтому их источник БД: project.json (и git) их не задаёт.
    team: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    shared_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Строка есть, а папки на томе нет: отмечает сверка на старте, проект при этом не пропадает из каталога.
    volume_missing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Где идут сборки соавторов личного проекта: на общих раннерах или на личных раннерах владельца.
    build_runners: Mapped[str] = mapped_column(String(16), nullable=False, server_default="shared")


class ProjectMemberRow(Base):
    __tablename__ = "project_members"
    __table_args__ = (Index("ix_project_members_principal", "principal_kind", "principal_id"),)

    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    principal_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    persona: Mapped[str | None] = mapped_column(String(64))
    can_share: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    show_sources: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    can_edit_all: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
