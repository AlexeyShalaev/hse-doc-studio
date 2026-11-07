"""Серверы ИИ-моделей, поставленные из админки: состояние установки живёт в базе и переживает перезапуск."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class ModelServerRow(Base):
    __tablename__ = "model_servers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    engine: Mapped[str] = mapped_column(String(16), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    target: Mapped[str] = mapped_column(String(8), nullable=False)
    # Сохранённый SSH-доступ (runner_ssh_credentials.id) либо пусто: без него удалённым сервером не управлять.
    credential_id: Mapped[str | None] = mapped_column(String(32))
    host: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    container: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    exposure: Mapped[str] = mapped_column(String(16), nullable=False, server_default="internal")
    endpoint: Mapped[str | None] = mapped_column(String(255))
    provider_id: Mapped[str | None] = mapped_column(String(36))
    image: Mapped[str] = mapped_column(String(200), nullable=False)
    # JSON {шаг: состояние}; секретов в записи нет.
    steps: Mapped[str] = mapped_column(Text, nullable=False, server_default="{}")
    percent: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String(400), nullable=False, server_default="")
    error: Mapped[str | None] = mapped_column(String(400))
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
