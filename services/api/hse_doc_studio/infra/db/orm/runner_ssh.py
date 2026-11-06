"""Сохранённые SSH-доступы для установки раннеров из админки: только по явной галочке, секрет шифртекстом."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.core.secrets import EncryptedColumn, encrypted_columns
from hse_doc_studio.infra.db.base import Base


class RunnerSshCredentialRow(Base):
    __tablename__ = "runner_ssh_credentials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    sudo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    auth_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    host_key_type: Mapped[str] = mapped_column(String(64), nullable=False)
    host_key_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    host_key_public: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    runner_name: Mapped[str | None] = mapped_column(String(64))
    # Шифртекст JSON с паролем или закрытым ключом и passphrase; привязка `column_aad(table, "secret_enc", id)`.
    secret_enc: Mapped[str] = mapped_column(Text, nullable=False)


encrypted_columns.register(EncryptedColumn("runner_ssh_credentials", "secret_enc", pk="id"))
