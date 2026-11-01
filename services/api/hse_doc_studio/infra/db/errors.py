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


class MigrationLockTimeoutError(RuntimeError):
    """Advisory-лок миграций занят другим процессом дольше отведённого срока."""


class DbAheadError(RuntimeError):
    """База новее кода: в ней ревизия, которой нет в цепочке миграций этого образа (код ``db_ahead``)."""

    code = "db_ahead"

    def __init__(self, current: str, head: str) -> None:
        self.current = current
        self.head = head
        super().__init__(
            f"db_ahead: ревизия базы {current} неизвестна этой версии приложения (ожидается {head}); "
            "запущен более старый образ, чем применённые миграции: верните новую версию, схему не трогаем"
        )
