"""Админка установки."""

from pydantic import BaseModel


class AdminConfig(BaseModel):
    """Ограничения админки (HSE_STUDIO__ADMIN__*). Поля добавляет срез админки."""
