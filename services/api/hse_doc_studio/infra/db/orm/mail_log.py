"""Журнал писем (docs/design/mail-log.md, 5.1): строка на каждую попытку отправить письмо, без тела и ссылок."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.mail.journal import MailCause, MailStatus
from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base

MAIL_STATUSES = tuple(status.value for status in MailStatus)
MAIL_CAUSES = tuple(cause.value for cause in MailCause)


class MailLogRow(Base):
    """Меняются только поля исхода автоповтора (раздел 14, V7). Внешних ключей нет: строка переживает удаление
    проекта, а стирание человека (`SqlUserLifecycle.erase`) удаляет его строки и обнуляет `actor_user_id` само."""

    __tablename__ = "mail_log"
    __table_args__ = (
        CheckConstraint(f"status IN {MAIL_STATUSES!r}", name="status"),
        CheckConstraint(f"cause IN {MAIL_CAUSES!r}", name="cause"),
        # Ушедшее письмо без Message-ID искать в логах почтового сервера нечем (то же в `MailLogEntry`).
        CheckConstraint("status <> 'sent' OR message_id IS NOT NULL", name="sent_message_id"),
        # Срок хранения и период.
        Index("ix_mail_log_at", "at"),
        # Журнал листается ключом id, новые сверху: фильтры по адресу, человеку и проекту идут в порядке страницы.
        Index("ix_mail_log_to_email_id", text("lower(to_email)"), text("id DESC")),
        Index(
            "ix_mail_log_to_user_id_id",
            "to_user_id",
            text("id DESC"),
            postgresql_where=text("to_user_id IS NOT NULL"),
        ),
        Index(
            "ix_mail_log_project_id_id",
            "project_id",
            text("id DESC"),
            postgresql_where=text("project_id IS NOT NULL"),
        ),
        # Счётчик неушедших за сутки (меню и сводка).
        Index("ix_mail_log_failed_at", "at", postgresql_where=text("status = 'failed'")),
        # Ручные повторы строки (V2) и ждущие автоповтора (V13), ml_04.
        Index("ix_mail_log_resent_from_id", "resent_from_id", postgresql_where=text("resent_from_id IS NOT NULL")),
        Index("ix_mail_log_next_attempt_at", "next_attempt_at", postgresql_where=text("next_attempt_at IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    lang: Mapped[str] = mapped_column(String(8), nullable=False)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    to_user_id: Mapped[str | None] = mapped_column(String(64))
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(32))
    smtp_code: Mapped[int | None] = mapped_column(SmallInteger)
    error_text: Mapped[str | None] = mapped_column(String(300))
    message_id: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default=text("1"))
    cause: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_user_id: Mapped[str | None] = mapped_column(String(64))
    task: Mapped[str | None] = mapped_column(String(64))
    origin: Mapped[str] = mapped_column(String(48), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64))
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    ref_kind: Mapped[str | None] = mapped_column(String(32))
    ref_id: Mapped[str | None] = mapped_column(String(64))
    params: Mapped[Any] = mapped_column(JSONB, nullable=False)
    template_digest: Mapped[str] = mapped_column(String(16), nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Без внешнего ключа: исходная строка может уйти по сроку хранения раньше повтора.
    resent_from_id: Mapped[int | None] = mapped_column(BigInteger)


class MailRetryRow(Base):
    """Очередь автоповтора (V8): запрос письма целиком шифртекстом, пока не будет исхода. Строка журнала уходит,
    уходит и строка очереди (каскад: срок хранения, стирание человека)."""

    __tablename__ = "mail_retry"
    __table_args__ = (Index("ix_mail_retry_due_at", "due_at"),)

    entry_id: Mapped[int] = mapped_column(ForeignKey("mail_log.id", ondelete="CASCADE"), primary_key=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_enc: Mapped[str] = mapped_column(Text, nullable=False)


encrypted_columns.register(EncryptedColumn("mail_retry", "request_enc", pk="entry_id"))
