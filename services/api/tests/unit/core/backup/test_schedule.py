from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.backup.errors import BackupError
from hse_doc_studio.core.backup.schedule import Schedule, ScheduleKind, is_due, next_run, parse_cron


def _t(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test__cron__daily_at_three__next_after_picks_following_day() -> None:
    cron = parse_cron("0 3 * * *")
    assert cron.next_after(_t("2026-11-01T02:59:30")) == _t("2026-11-01T03:00")
    assert cron.next_after(_t("2026-11-01T03:00")) == _t("2026-11-02T03:00")


def test__cron__steps_lists_and_ranges() -> None:
    cron = parse_cron("*/15 9-10 * * 1,3")  # понедельник и среда
    nxt = cron.next_after(_t("2026-11-02T08:00"))  # 2026-11-02 это понедельник
    assert nxt == _t("2026-11-02T09:00")
    assert cron.next_after(_t("2026-11-02T10:45")) == _t("2026-11-04T09:00")


def test__cron__sunday_as_zero_and_seven() -> None:
    assert parse_cron("0 0 * * 0").weekdays == parse_cron("0 0 * * 7").weekdays == frozenset({0})
    assert parse_cron("0 12 * * 0").next_after(_t("2026-11-01T00:00")) == _t("2026-11-01T12:00")  # воскресенье


def test__cron__day_of_month_and_weekday_both_restricted__either_matches() -> None:
    cron = parse_cron("0 0 13 * 5")  # 13-е или пятница
    assert cron.next_after(_t("2026-11-01T00:00")) == _t("2026-11-06T00:00")


def test__cron__month_roll_over_and_leap_day() -> None:
    assert parse_cron("0 0 1 1 *").next_after(_t("2026-11-05T00:00")) == _t("2027-01-01T00:00")
    assert parse_cron("0 0 29 2 *").next_after(_t("2026-11-05T00:00")) == _t("2028-02-29T00:00")


@pytest.mark.parametrize(
    "bad",
    ["", "* * * *", "61 * * * *", "* 24 * * *", "* * 0 * *", "* * * 13 *", "a * * * *", "*/0 * * * *", "5-3 * * * *"],
)
def test__cron__invalid__rejected(bad: str) -> None:
    with pytest.raises(BackupError):
        parse_cron(bad)


def test__schedule__interval_out_of_range__rejected() -> None:
    with pytest.raises(BackupError):
        Schedule(ScheduleKind.interval, interval_hours=0)
    with pytest.raises(BackupError):
        Schedule(ScheduleKind.cron, cron="nope")


def test__is_due__interval() -> None:
    schedule = Schedule(ScheduleKind.interval, interval_hours=6)
    now = _t("2026-11-01T12:00")
    assert is_due(schedule, None, now)
    assert not is_due(schedule, now - timedelta(hours=5, minutes=59), now)
    assert is_due(schedule, now - timedelta(hours=6), now)


def test__is_due__cron_missed_runs_collapse_into_one() -> None:
    schedule = Schedule(ScheduleKind.cron, cron="0 3 * * *")
    last = _t("2026-10-25T03:00")
    now = _t("2026-11-01T10:00")
    assert is_due(schedule, last, now)
    assert not is_due(schedule, now, now + timedelta(hours=1))


def test__next_run__reports_following_firing() -> None:
    schedule = Schedule(ScheduleKind.cron, cron="30 4 * * *")
    last = _t("2026-11-01T04:30")
    assert next_run(schedule, last, _t("2026-11-01T10:00")) == _t("2026-11-02T04:30")
    interval = Schedule(ScheduleKind.interval, interval_hours=24)
    assert next_run(interval, last, _t("2026-11-01T10:00")) == _t("2026-11-02T04:30")
