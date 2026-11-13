"""Даты подписания: пояс отображения и тексты меток даты (docs/design/signing-route.md, 14.3 и 14.4).

Все даты подписи и версии показываются по Москве: у проекта и установки своего пояса нет. Если пояс проекта
появится, его возьмёт этот модуль. Им пользуются метки даты (`stamps_for_doc`), даты версии в пакете
(`package_text.version_date`) и дата в рамке подписи (`sign_date`, эффект маршрута).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from hse_doc_studio.core.enums import DateMarkFormat

# Длина ISO-дня «2026-11-13»: так записана ручная дата подписи (`SignedAt.at` у `manual`).
_ISO_DAY_LEN = 10

# Сколько меток даты у слота документа (14.7) и лист, в который рамка метки из пака обязана влезть (14.10, A4).
MAX_DATE_MARKS = 8
SHEET_WIDTH_MM = 210.0
SHEET_HEIGHT_MM = 297.0


def frame_problem(  # noqa: PLR0913 — рамка на странице
    page: int, x_mm: float, y_mm: float, width_mm: float, height_mm: float, sheet: tuple[float, float] | None
) -> str | None:
    """Почему рамка метки даты не годится (по-английски, для журнала и линтера пака); None, если годится.

    Страница с 1, рамка ненулевая и не уходит за левый и верхний край; с `sheet` (ширина и высота листа в мм) ещё
    и за правый и нижний.
    """
    if page < 1:
        return f"page {page} is before the first page"
    if width_mm <= 0 or height_mm <= 0:
        return "the box has no size"
    if x_mm < 0 or y_mm < 0:
        return "the box is past the top or left edge"
    if sheet is not None and (x_mm + width_mm > sheet[0] + 0.01 or y_mm + height_mm > sheet[1] + 0.01):
        return f"the box is past the edge of the {sheet[0]:g} x {sheet[1]:g} mm page"
    return None


MONTHS_GENITIVE_RU = (
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
)
MONTHS_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def display_zone() -> tzinfo:
    """Пояс дат подписи и версии: московское время, как у людей в интерфейсе.

    Без базы поясов (нет tzdata в образе) берётся постоянное смещение UTC+3: переходов на летнее время в Москве нет.
    """
    try:
        return ZoneInfo("Europe/Moscow")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=3), "MSK")


DISPLAY_ZONE = display_zone()


def to_display(moment: datetime) -> datetime:
    """Момент в поясе отображения; время без пояса считается UTC (так пишет его Студия)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(DISPLAY_ZONE)


def display_day(value: datetime | date | str) -> date | None:
    """День подписи по Москве; None, если значение не разобрать.

    Момент (`datetime` или ISO со временем) переводится в пояс отображения: согласие в 23:30 UTC это следующий день
    по Москве. Просто день (`date` или «2026-11-13», ручная дата автора) остаётся тем же днём.
    """
    if isinstance(value, datetime):
        return to_display(value).date()
    if isinstance(value, date):
        return value
    text = value.strip()
    try:
        if len(text) == _ISO_DAY_LEN:
            return date.fromisoformat(text)
        return to_display(datetime.fromisoformat(text)).date()
    except ValueError:
        return None


def format_numeric(day: date) -> str:
    """«13.11.2026»: день и месяц с ведущим нулём."""
    return f"{day.day:02d}.{day.month:02d}.{day.year}"


def format_day(day: date, fmt: DateMarkFormat, lang: str) -> str:
    """Текст метки даты для дня `day` в формате `fmt`; месяц словом по языку документа (ru в родительном падеже)."""
    en = lang == "en"
    month = (MONTHS_EN if en else MONTHS_GENITIVE_RU)[day.month - 1]
    texts = {
        DateMarkFormat.day: str(day.day),
        DateMarkFormat.month_word: month,
        DateMarkFormat.month_number: f"{day.month:02d}",
        DateMarkFormat.year: str(day.year),
        DateMarkFormat.year_short: f"{day.year % 100:02d}",
        DateMarkFormat.date_numeric: format_numeric(day),
        DateMarkFormat.date_long: f"{day.day} {month} {day.year}" + ("" if en else " г."),
    }
    return texts[fmt]


def format_date_mark(moment: datetime | date | str, fmt: DateMarkFormat, lang: str) -> str | None:
    """Что напечатает метка даты формата `fmt` для момента подписи `moment`; None, если момент не разобрать."""
    day = display_day(moment)
    return format_day(day, fmt, lang) if day is not None else None


def format_moment(value: str) -> str | None:
    """Момент ISO 8601 по Москве: «2026-11-14T07:05:00Z» → «14.11.2026 10:05»; без времени или неразборчивый None."""
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if len(value.strip()) == _ISO_DAY_LEN:
        return None
    shown = to_display(moment)
    return f"{format_numeric(shown.date())} {shown.hour:02d}:{shown.minute:02d}"
