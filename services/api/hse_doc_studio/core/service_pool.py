"""Ошибки пула сервисов: интерактивные сервисы (LanguageTool) делят несколько реплик между пользователями."""

from __future__ import annotations


class ServicePoolError(Exception):
    """Базовая ошибка пула; `retry_after_s` подсказывает клиенту, когда повторить запрос."""

    def __init__(self, message: str, retry_after_s: int = 1) -> None:
        super().__init__(message)
        self.retry_after_s = max(1, retry_after_s)


class ServiceBusyError(ServicePoolError):
    """Пользователь исчерпал свою долю или все реплики заняты: HTTP 429 с `Retry-After`."""


class ServiceUnavailableError(ServicePoolError):
    """Нет ни одной здоровой реплики (цепь разомкнута или реплик не настроено): HTTP 503."""
