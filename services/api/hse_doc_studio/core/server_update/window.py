"""Окно обслуживания: дни недели и время суток в UTC, окно может переходить через полночь."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

DAY_MINUTES = 24 * 60


def in_window(now: datetime, days: Sequence[int], start_min: int, minutes: int) -> bool:
    """Попадает ли `now` (UTC) в окно. Пустой список дней значит «никогда», 24 часа значат «всегда в эти дни».

    День недели относится к началу окна: окно «суббота 23:00, 180 минут» заканчивается в воскресенье 02:00 и
    воскресенью принадлежит только по началу.
    """
    if not days or minutes <= 0:
        return False
    minute_of_day = now.hour * 60 + now.minute
    weekday = now.weekday()
    if minutes >= DAY_MINUTES:
        return weekday in days
    since_start = (minute_of_day - start_min) % DAY_MINUTES
    if since_start >= minutes:
        return False
    started_on_previous_day = minute_of_day < start_min
    start_weekday = (weekday - 1) % 7 if started_on_previous_day else weekday
    return start_weekday in days


def next_window_start(now: datetime, days: Sequence[int], start_min: int, minutes: int) -> datetime | None:
    """Ближайшее начало окна не раньше `now`; внутри окна возвращает `now`. Нет дней значит нет окна."""
    if not days or minutes <= 0:
        return None
    if in_window(now, days, start_min, minutes):
        return now
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for offset in range(8):
        candidate = midnight + timedelta(days=offset, minutes=start_min)
        if candidate > now and candidate.weekday() in days:
            return candidate
    return None
