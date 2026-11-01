"""Расписание бэкапов: интервал или cron из пяти полей (UTC). Чистые функции без часов и базы."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from hse_doc_studio.core.backup.errors import BackupError, BackupErrorCode


class ScheduleKind(StrEnum):
    interval = "interval"
    cron = "cron"


_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))  # день недели: 0 и 7 это воскресенье
_FIELD_NAMES = ("minute", "hour", "day", "month", "weekday")
_MAX_SEARCH = timedelta(days=366 * 5)
MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 24 * 90


def _bad(field: str) -> BackupError:
    return BackupError(BackupErrorCode.invalid_input, f"cron: bad field {field}", field="cron")


def _parse_step(raw: str, name: str) -> int:
    if not raw.isdigit() or int(raw) < 1:
        raise _bad(name)
    return int(raw)


def _parse_item(part: str, low: int, high: int, name: str) -> range:
    body, _, raw_step = part.partition("/")
    step = _parse_step(raw_step, name) if "/" in part else 1
    if body == "*":
        start, end = low, high
    elif "-" in body:
        raw_start, _, raw_end = body.partition("-")
        if not (raw_start.isdigit() and raw_end.isdigit()):
            raise _bad(name)
        start, end = int(raw_start), int(raw_end)
    elif body.isdigit():
        start = int(body)
        end = high if "/" in part else start
    else:
        raise _bad(name)
    if not low <= start <= end <= high:
        raise _bad(name)
    return range(start, end + 1, step)


def _parse_field(text: str, low: int, high: int, name: str) -> frozenset[int]:
    values: set[int] = set()
    for part in text.split(","):
        values.update(_parse_item(part, low, high, name))
    if name == "weekday":
        values = {v % 7 for v in values}
    return frozenset(values)


@dataclass(frozen=True)
class CronExpr:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    day_any: bool
    weekday_any: bool
    text: str

    def _day_ok(self, moment: datetime) -> bool:
        weekday = (moment.weekday() + 1) % 7  # cron: 0 это воскресенье
        in_days = moment.day in self.days
        in_weekdays = weekday in self.weekdays
        # Как в классическом cron: если ограничены оба поля, подходит любое из двух.
        if not self.day_any and not self.weekday_any:
            return in_days or in_weekdays
        return in_days and in_weekdays

    def matches(self, moment: datetime) -> bool:
        return (
            moment.minute in self.minutes
            and moment.hour in self.hours
            and moment.month in self.months
            and self._day_ok(moment)
        )

    def next_after(self, moment: datetime) -> datetime | None:
        """Ближайшее срабатывание строго после `moment` (минутная точность, UTC); None, если в ближайшие годы нет."""
        current = moment.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
        limit = current + _MAX_SEARCH
        while current < limit:
            if current.month not in self.months:
                current = (current.replace(day=1, hour=0, minute=0) + timedelta(days=32)).replace(day=1)
                continue
            if not self._day_ok(current):
                current = current.replace(hour=0, minute=0) + timedelta(days=1)
                continue
            if current.hour not in self.hours:
                current = current.replace(minute=0) + timedelta(hours=1)
                continue
            if current.minute not in self.minutes:
                current += timedelta(minutes=1)
                continue
            return current
        return None


def parse_cron(text: str) -> CronExpr:
    fields = text.split()
    if len(fields) != len(_RANGES):
        raise BackupError(BackupErrorCode.invalid_input, "cron: five fields expected", field="cron")
    parsed = [
        _parse_field(raw, low, high, name) for raw, (low, high), name in zip(fields, _RANGES, _FIELD_NAMES, strict=True)
    ]
    return CronExpr(
        minutes=parsed[0],
        hours=parsed[1],
        days=parsed[2],
        months=parsed[3],
        weekdays=parsed[4],
        day_any=fields[2].startswith("*"),
        weekday_any=fields[4].startswith("*"),
        text=" ".join(fields),
    )


@dataclass(frozen=True)
class Schedule:
    kind: ScheduleKind = ScheduleKind.interval
    interval_hours: int = 24
    cron: str = "0 3 * * *"

    def __post_init__(self) -> None:
        if not MIN_INTERVAL_HOURS <= self.interval_hours <= MAX_INTERVAL_HOURS:
            raise BackupError(BackupErrorCode.invalid_input, "interval out of range", field="interval_hours")
        if self.kind is ScheduleKind.cron:
            parse_cron(self.cron)


def is_due(schedule: Schedule, last_scheduled_at: datetime | None, now: datetime) -> bool:
    """Пора ли запускать плановый бэкап. Пропущенные срабатывания сливаются в одно; первый запуск ждёт срабатывания."""
    if schedule.kind is ScheduleKind.interval:
        if last_scheduled_at is None:
            return True
        return now - last_scheduled_at >= timedelta(hours=schedule.interval_hours)
    if last_scheduled_at is None:
        return True
    following = parse_cron(schedule.cron).next_after(last_scheduled_at)
    return following is not None and following <= now


def next_run(schedule: Schedule, last_scheduled_at: datetime | None, now: datetime) -> datetime | None:
    """Когда сработает расписание (для подписи в админке); None, если срабатывания не найти."""
    if schedule.kind is ScheduleKind.interval:
        if last_scheduled_at is None:
            return now
        return max(now, last_scheduled_at + timedelta(hours=schedule.interval_hours))
    base = last_scheduled_at or now
    following = parse_cron(schedule.cron).next_after(base)
    if following is None:
        return None
    return max(following, now) if last_scheduled_at else following
