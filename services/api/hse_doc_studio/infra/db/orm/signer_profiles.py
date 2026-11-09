"""Профили подписантов: картинка подписи и открытая часть ключа для плашки, одна строка на человека.

Закрытых ключей здесь нет by design: сценарий отвергает файл с закрытым ключом до записи, поэтому шифровать нечего.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from hse_doc_studio.infra.db.base import Base


class SignerProfileRow(Base):
    """Профиль исчезает вместе с пользователем."""

    __tablename__ = "signer_profiles"
    __table_args__ = (CheckConstraint("key_kind IN ('x509', 'openpgp')", name="key_kind"),)

    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    image_png: Mapped[bytes | None] = mapped_column(LargeBinary)
    image_sha256: Mapped[str | None] = mapped_column(String(64))
    image_width_px: Mapped[int | None] = mapped_column(Integer)
    image_height_px: Mapped[int | None] = mapped_column(Integer)
    image_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Сертификат X.509 в PEM или открытый ключ OpenPGP как загружен.
    key_kind: Mapped[str | None] = mapped_column(String(16))
    key_data: Mapped[bytes | None] = mapped_column(LargeBinary)
    # Данные плашки из ключа (SignerInfo): маршрут читает их без gpg и без разбора сертификата.
    key_plate: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    key_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
