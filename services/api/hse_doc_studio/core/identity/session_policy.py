"""Сроки сессий и задержки при неудачных входах."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

Clock = Callable[[], datetime]

FREE_FAILURES = 5
MAX_LOGIN_DELAY = timedelta(minutes=15)


@dataclass(frozen=True)
class SessionPolicy:
    """Скользящий срок (idle) ограничен абсолютным: активная сессия всё равно живёт не дольше `absolute`."""

    idle: timedelta = timedelta(days=7)
    absolute: timedelta = timedelta(days=30)
    # Не чаще этого интервала сдвигаем срок в БД, чтобы запрос не превращался в запись.
    touch_interval: timedelta = timedelta(minutes=5)


def login_delay(failures: int) -> timedelta:
    """Задержка после `failures`-й неудачи: первые четыре бесплатны, с пятой 1 с, 2 с, 4 с ... до 15 минут.

    Постоянной блокировки нет: иначе чужими неудачными попытками можно запереть жертву.
    """
    over = failures - FREE_FAILURES
    if over < 0:
        return timedelta(0)
    return min(timedelta(seconds=2 ** min(over, 20)), MAX_LOGIN_DELAY)


def utc_now() -> datetime:
    return datetime.now(UTC)
