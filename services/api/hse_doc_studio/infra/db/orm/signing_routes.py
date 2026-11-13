"""Маршруты подписания (docs/design/signing-route.md, раздел 5.8): маршрут, его документы, участники и события.

Пользователи (`created_by`, `sent_by`, `user_id`, `actor_id`) хранятся в виде `users.id` (32 hex-символа) без
внешнего ключа: маршрут это история, удаление человека её не переписывает, а ушедшего участника расчёт замечает
по персонам проекта. Приглашение тоже без ключа: оно живёт в том же проекте и удаляется вместе с ним.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base

# Значения перечислений `core.signing_route.entities`; миграции sr_01 и sr_09 повторяют их литералами.
ROUTE_STATUSES = ("draft", "active", "paused", "returned", "completed", "cancelled", "archived")
ROUTE_PHASES = ("approval", "signing", "done")
STOP_REASONS = ("rebuilt", "frozen_changed", "marks_changed", "participant_left", "returned", "sent_changed")
# OPEN_STATUSES: незавершённый маршрут точки сдачи один.
OPEN_WHERE = "status IN ('draft', 'active', 'paused', 'returned')"
# WATCHING_STATUSES: маршруты, которые сверяют документы со снимком.
WATCHING_WHERE = "status IN ('active', 'completed')"


class SigningRouteRow(Base):
    __tablename__ = "signing_routes"
    __table_args__ = (
        CheckConstraint(f"status IN {ROUTE_STATUSES}", name="status"),
        CheckConstraint(f"phase IS NULL OR phase IN {ROUTE_PHASES}", name="phase"),
        CheckConstraint(f"stop_reason IS NULL OR stop_reason IN {STOP_REASONS}", name="stop_reason"),
        Index("ux_signing_routes_open", "project_id", "profile_id", unique=True, postgresql_where=text(OPEN_WHERE)),
        Index("ix_signing_routes_project_profile", "project_id", "profile_id", text("created_at DESC")),
        Index("ix_signing_routes_watching", "project_id", postgresql_where=text(WATCHING_WHERE)),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str | None] = mapped_column(String(16))
    round: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Снимок отпечатков: список объектов doc_id, compiled_sha256, marks_digest, frozen_sha256, sent_at по документам.
    snapshot: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default="[]")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message: Mapped[str | None] = mapped_column(Text)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    # Участник маршрута (signing_route_participants.id), чей возврат или уход остановил маршрут.
    stopped_by: Mapped[UUID | None] = mapped_column(Uuid)
    # Версия шаблона, по пресету которой собран состав (signing-route.md, 15.7); NULL: не по пресету.
    preset_version: Mapped[str | None] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_by: Mapped[str | None] = mapped_column(String(64))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Оптимистическая блокировка: запись только поверх прочитанной версии (SigningRoute.version).
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class SigningRouteDocRow(Base):
    """Документы маршрута; `active` у маршрутов из HOLDING_STATUSES: документ держит один маршрут."""

    __tablename__ = "signing_route_docs"
    __table_args__ = (
        Index("ux_signing_route_docs_active", "project_id", "doc_id", unique=True, postgresql_where=text("active")),
    )

    route_id: Mapped[UUID] = mapped_column(ForeignKey("signing_routes.id", ondelete="CASCADE"), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    # Копия signing_routes.project_id для уникального индекса по документу проекта.
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class SigningRouteParticipantRow(Base):
    __tablename__ = "signing_route_participants"
    __table_args__ = (
        Index("ix_signing_route_participants_route", "route_id", "position"),
        Index("ix_signing_route_participants_user", "user_id", postgresql_where=text("user_id IS NOT NULL")),
        Index(
            "ix_signing_route_participants_invitation",
            "invitation_id",
            postgresql_where=text("invitation_id IS NOT NULL"),
        ),
    )

    # Id участника уникален в своём маршруте: новый маршрут точки может взять состав прежнего вместе с id.
    route_id: Mapped[UUID] = mapped_column(ForeignKey("signing_routes.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Порядок в редакторе маршрута; шаг задаёт `step`.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    persona: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(64))
    invitation_id: Mapped[str | None] = mapped_column(String(64))
    # Пары «документ, слот» участника: список объектов doc_id и slot_id.
    assignments: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default="[]")
    # Согласие: раунд, отпечатки (список объектов doc_id и token), время, фаза.
    approval: Mapped[Any | None] = mapped_column(JSONB)
    # Последний запрос участнику: раунд, ход (outcome), время.
    notified: Mapped[Any | None] = mapped_column(JSONB)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reminders: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Пропуск автором (signing-route.md, 13.3): раунд, время, кто, пары, метки; NULL: не пропущен. sr_11_skip.
    skipped: Mapped[Any | None] = mapped_column(JSONB(none_as_null=True))


class SigningRouteEventRow(Base):
    __tablename__ = "signing_route_events"
    __table_args__ = (Index("ix_signing_route_events_route", "route_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    route_id: Mapped[UUID] = mapped_column(ForeignKey("signing_routes.id", ondelete="CASCADE"), nullable=False)
    round: Mapped[int] = mapped_column(Integer, nullable=False)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64))
    # Участник, к которому событие относится; без ключа: история переживает правку состава маршрута.
    participant_id: Mapped[UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[Any] = mapped_column(JSONB, nullable=False, server_default="{}")
