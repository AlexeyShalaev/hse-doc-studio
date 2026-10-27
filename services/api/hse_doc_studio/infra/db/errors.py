"""Ошибки слоя БД."""

from __future__ import annotations


class DbConfigError(RuntimeError):
    """Не задан или неверен DSN."""


class DbOutdatedError(RuntimeError):
    """Схема базы не соответствует версии приложения (код ``db_outdated``)."""

    code = "db_outdated"

    def __init__(self, current: str | None, head: str) -> None:
        self.current = current
        self.head = head
        super().__init__(
            f"db_outdated: ревизия базы {current or 'пусто'}, ожидается {head}; "
            "выполните `hse-doc-studio db upgrade` или включите HSE_STUDIO__DB__AUTO_MIGRATE"
        )
