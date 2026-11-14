"""Студия шаблонов (docs/design/template-studio.md, 4.1 и 3.3): рабочие пространства и право «Автор шаблонов».

Пространство исчезает вместе с владельцем; ссылка на git-доступ обнуляется, если доступ удалён (выборка тогда идёт
без токена и честно падает `credentials_missing`). Право выдаётся человеку или группе организации, ровно одному из них,
и исчезает вместе с ним.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.pack_studio.entities import WorkspaceKind, WorkspaceState
from hse_doc_studio.infra.db.base import Base

WORKSPACE_KINDS = tuple(kind.value for kind in WorkspaceKind)
WORKSPACE_STATES = tuple(state.value for state in WorkspaceState)


class PackWorkspaceRow(Base):
    __tablename__ = "pack_workspaces"
    __table_args__ = (
        CheckConstraint(f"kind IN {WORKSPACE_KINDS!r}", name="kind"),
        CheckConstraint(f"state IN {WORKSPACE_STATES!r}", name="state"),
        Index("ix_pack_workspaces_owner_created", "owner_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    packs_path: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    # Адрес без секретов (`RemoteUrl.display_url`).
    remote_url: Mapped[str | None] = mapped_column(Text)
    credential_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("git_credentials.id", ondelete="SET NULL"))
    insecure_http: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    base_branch: Mapped[str | None] = mapped_column(Text)
    base_sha: Mapped[str | None] = mapped_column(String(64))
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Срез T6: рабочая ветка, запрос на слияние, последний статус проверок хостинга.
    work_branch: Mapped[str | None] = mapped_column(Text)
    pr_url: Mapped[str | None] = mapped_column(Text)
    pr_number: Mapped[int | None] = mapped_column(Integer)
    ci_status: Mapped[str | None] = mapped_column(String(32))
    # Папка на диске бывает только у локальной установки; колонка держит форму записи общей.
    folder: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PackStudioGrantRow(Base):
    __tablename__ = "pack_studio_grants"
    __table_args__ = (
        CheckConstraint("(user_id IS NULL) <> (group_id IS NULL)", name="one_subject"),
        Index("ux_pack_studio_grants_user", "user_id", unique=True, postgresql_where=text("user_id IS NOT NULL")),
        Index("ux_pack_studio_grants_group", "group_id", unique=True, postgresql_where=text("group_id IS NOT NULL")),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"))
    group_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("groups.id", ondelete="CASCADE"))
    granted_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
