"""Даты подписания: пояс отображения и тексты меток даты (docs/design/signing-route.md, 14.3 и 14.4)."""

from __future__ import annotations

import zoneinfo
from datetime import UTC, date, datetime, timedelta

import pytest
from hse_doc_studio.core.enums import DateMarkFormat
from hse_doc_studio.core.signatures import dates
from hse_doc_studio.core.signatures.dates import (
    MONTHS_EN,
    MONTHS_GENITIVE_RU,
    display_day,
    display_zone,
    format_date_mark,
    format_day,
    format_moment,
    frame_problem,
)
from hse_doc_studio.core.signatures.package_text import version_date

_F = DateMarkFormat


@pytest.mark.parametrize(
    ("fmt", "ru", "en"),
    [
        (_F.day, "13", "13"),
        (_F.month_word, "ноября", "November"),
        (_F.month_number, "11", "11"),
        (_F.year, "2026", "2026"),
        (_F.year_short, "26", "26"),
        (_F.date_numeric, "13.11.2026", "13.11.2026"),
        (_F.date_long, "13 ноября 2026 г.", "13 November 2026"),
    ],
)
def test__format_day__every_format__ru_and_en(fmt: DateMarkFormat, ru: str, en: str) -> None:
    day = date(2026, 11, 13)

    assert (format_day(day, fmt, "ru"), format_day(day, fmt, "en")) == (ru, en)


def test__format_day__single_digit_day_month_and_year__day_without_zero_month_and_year_with_zero() -> None:
    day = date(2005, 3, 3)

    assert [format_day(day, f, "ru") for f in _F] == ["3", "марта", "03", "2005", "05", "03.03.2005", "3 марта 2005 г."]


def test__months__genitive_ru_and_english_for_every_month() -> None:
    ru = [format_day(date(2026, m, 1), _F.month_word, "ru") for m in range(1, 13)]
    en = [format_day(date(2026, m, 1), _F.month_word, "en") for m in range(1, 13)]

    assert ru == [
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    assert en == list(MONTHS_EN)
    assert tuple(ru) == MONTHS_GENITIVE_RU


def test__unknown_language__russian_month() -> None:
    assert format_day(date(2026, 11, 13), _F.month_word, "de") == "ноября"


def test__day_boundary__23_30_utc_is_the_next_day_in_moscow() -> None:
    moment = datetime(2026, 11, 12, 23, 30, tzinfo=UTC)

    assert display_day(moment) == date(2026, 11, 13)
    assert format_date_mark("2026-11-12T23:30:00Z", _F.day, "ru") == "13"
    assert format_date_mark("2026-11-12T23:30:00+00:00", _F.date_long, "ru") == "13 ноября 2026 г."
    # Время без пояса Студия пишет в UTC.
    assert format_date_mark("2026-11-12T21:00:00", _F.date_numeric, "ru") == "13.11.2026"
    assert format_date_mark("2026-11-12T20:59:00Z", _F.date_numeric, "ru") == "12.11.2026"


def test__manual_day__stays_that_day_and_unparsable_gives_none() -> None:
    assert format_date_mark("2026-11-13", _F.date_numeric, "ru") == "13.11.2026"
    assert display_day(date(2026, 1, 31)) == date(2026, 1, 31)
    assert format_date_mark("13 ноября", _F.day, "ru") is None


def test__format_moment__moscow_time_and_day_only_or_garbage_gives_none() -> None:
    assert format_moment("2026-11-14T07:05:00Z") == "14.11.2026 10:05"
    assert format_moment("2026-11-14T22:30:00+00:00") == "15.11.2026 01:30"
    assert format_moment("2026-11-14") is None
    assert format_moment("вчера") is None


def test__version_date__uses_the_same_zone() -> None:
    assert version_date("2026-11-10T21:30:00Z") == "11.11.2026"
    assert version_date("10 ноября") == "10 ноября"


def test__without_tzdata__fixed_utc_plus_3(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing(_key: str) -> zoneinfo.ZoneInfo:
        raise zoneinfo.ZoneInfoNotFoundError("no tzdata")

    monkeypatch.setattr(dates, "ZoneInfo", missing)
    zone = display_zone()
    monkeypatch.setattr(dates, "DISPLAY_ZONE", zone)

    assert zone.utcoffset(None) == timedelta(hours=3)
    assert format_date_mark("2026-11-12T23:30:00Z", _F.date_numeric, "ru") == "13.11.2026"
    assert format_date_mark("2026-07-12T20:30:00Z", _F.date_numeric, "ru") == "12.07.2026"
    assert format_moment("2026-07-12T21:05:00Z") == "13.07.2026 00:05"


def test__frame_problem__page_size_and_edges() -> None:
    a4 = (210.0, 297.0)

    assert frame_problem(1, 120, 250, 8, 5, a4) is None
    assert frame_problem(1, 0, 0, 210, 297, a4) is None
    assert frame_problem(0, 10, 10, 8, 5, a4) == "page 0 is before the first page"
    assert frame_problem(1, 10, 10, 0, 5, a4) == "the box has no size"
    assert frame_problem(1, -1, 10, 8, 5, None) == "the box is past the top or left edge"
    assert frame_problem(1, 205, 10, 8, 5, a4) == "the box is past the edge of the 210 x 297 mm page"
    assert frame_problem(9, 205, 10, 8, 5, None) is None
