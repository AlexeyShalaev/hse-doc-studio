"""Доверие к git-серверам на уровне установки: настройки хостов и ключи ssh."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class GitHostSettingsRow(Base):
    """Подмена провайдера, свой CA и закреплённый сертификат сервера. Меняет только админ установки."""

    __tablename__ = "git_host_settings"

    # `host` или `host:port`, как у JSON-файла; порт https по умолчанию в ключ не входит.
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int | None] = mapped_column(Integer)
    provider_override: Mapped[str | None] = mapped_column(String(32))
    ca_pem: Mapped[str | None] = mapped_column(Text)
    pinned_fingerprint: Mapped[str | None] = mapped_column(Text)
    pinned_pem: Mapped[str | None] = mapped_column(Text)
    detected: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    updated_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GitKnownHostRow(Base):
    """Ключ ssh сервера, которому доверяет установка. Запись появляется после подтверждения отпечатка человеком."""

    __tablename__ = "git_known_hosts"

    # Имя в формате known_hosts: `host` или `[host]:port`.
    pattern: Mapped[str] = mapped_column(Text, primary_key=True)
    key_type: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), primary_key=True)
    host: Mapped[str] = mapped_column(Text, nullable=False)
    port: Mapped[int | None] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    trusted_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.id", ondelete="SET NULL"))
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
