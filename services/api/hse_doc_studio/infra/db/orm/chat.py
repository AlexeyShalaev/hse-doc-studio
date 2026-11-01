"""Личные чаты ИИ-агента на сервере: сессии, реплики, сводки уплотнения и записи ходов."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class ChatSessionRow(Base):
    """Чат принадлежит автору и проекту: исчезает вместе с любым из них."""

    __tablename__ = "chat_sessions"
    __table_args__ = (Index("ix_chat_sessions_owner_scope", "owner_id", "is_system", "project_id", "updated_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    # Чат системного агента может быть не привязан к проекту; привязанный исчезает вместе с проектом.
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    owner_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    doc_id: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    # Провайдеры ИИ переедут в БД отдельным срезом, пока это просто идентификатор без внешнего ключа.
    default_provider_id: Mapped[UUID | None] = mapped_column(Uuid)
    default_model: Mapped[str | None] = mapped_column(String(256))
    persona: Mapped[str | None] = mapped_column(String(128))
    persona_instructions: Mapped[str | None] = mapped_column(Text)
    # Счётчик же и есть следующий seq: его выдаёт только append_message одним UPDATE ... RETURNING.
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_run_id: Mapped[UUID | None] = mapped_column(Uuid)
    compacted_through_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="-1")
    summary_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estimated_context_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ChatMessageRow(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (UniqueConstraint("session_id", "seq", name="uq_chat_messages_session_seq"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    run_id: Mapped[UUID | None] = mapped_column(Uuid)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    blocks: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model: Mapped[str | None] = mapped_column(String(256))
    provider_id: Mapped[UUID | None] = mapped_column(Uuid)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    approval: Mapped[str] = mapped_column(String(32), nullable=False, server_default="auto")
    compacted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class ChatSummaryRow(Base):
    __tablename__ = "chat_summaries"
    __table_args__ = (Index("ix_chat_summaries_session_created", "session_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    covers_from_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    covers_to_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    model: Mapped[str | None] = mapped_column(String(256))
    token_estimate: Mapped[int | None] = mapped_column(Integer)


class AgentRunRow(Base):
    __tablename__ = "chat_agent_runs"
    __table_args__ = (
        Index("ix_chat_agent_runs_session_created", "session_id", "created_at"),
        Index(
            "ix_chat_agent_runs_unfinished",
            "session_id",
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trigger_seq: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    first_emitted_seq: Mapped[int | None] = mapped_column(Integer)
    last_emitted_seq: Mapped[int | None] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String(256))
    provider_id: Mapped[UUID | None] = mapped_column(Uuid)
    iterations: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    diagnostics: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, server_default="[]")
