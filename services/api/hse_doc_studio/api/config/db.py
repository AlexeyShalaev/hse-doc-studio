"""Подключение к Postgres."""

from pydantic import BaseModel


class DbConfig(BaseModel):
    """Postgres серверного режима (HSE_STUDIO__DB__*). Поля добавляет срез персистентности."""
