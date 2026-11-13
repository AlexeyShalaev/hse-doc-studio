"""Сроки контрольных точек (docs/design/signing-route.md, раздел 16).

Срок точки задаёт пользователь для своего проекта (`Project.deadlines`), пак даёт точке только подсказку текстом
(`SubmissionProfile.deadline_hint`). Здесь разбор срока, его состояние для точки, списка проектов и MCP (16.6) и
проверка подсказки пака (16.4): одно определение для API, лоадера, `pack_lint` и напоминания (R29). Здесь же срок
нового черновика маршрута из срока точки (16.5) и правила напоминания автору `checkpoint_due` (16.7).

Состояние считается по Москве (`DISPLAY_ZONE`, 14.4): «сегодня» значит, что срок приходится на сегодняшний день по
Москве и ещё не наступил, «скоро» на один из трёх следующих дней. После срока точка «пакет собран», если пакет этой
точки собран за 14 дней до срока и не позже него, иначе «просрочено». Сдал ли студент работу в ЛМС, Студия не знает.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE

# «Скоро»: срок в один из этих календарных дней по Москве, считая от завтра (16.6).
SOON_DAYS = 3
# Пакет точки считается собранным к сроку, если собран не раньше этого до срока (черновые сборки не в счёт).
PACKAGE_WINDOW = timedelta(days=14)
# Список проектов: ближайший срок не дальше этого, иначе просрочка не старше `LIST_OVERDUE`.
LIST_AHEAD = timedelta(days=30)
LIST_OVERDUE = timedelta(days=7)
# Срок раньше этого года это опечатка, а не срок точки.
MIN_YEAR = 2000
# Подсказка пака (16.4): обе локали, не длиннее этого.
HINT_LANGS = ("ru", "en")
HINT_MAX_LEN = 200

# Срок маршрута на столько раньше срока точки (16.5), если до срока точки не меньше `ROUTE_MARGIN_MIN`.
ROUTE_MARGIN = timedelta(days=1)
ROUTE_MARGIN_MIN = timedelta(days=2)
# Напоминание автору за столько суток до срока точки (16.7); настройка `checkpoint.reminder_days`.
REMINDER_DAYS = 3
# Ключ повтора уведомления не длиннее колонки `notifications.dedupe_key`.
_KEY_MAX = 128

BAD_DEADLINE = "bad_deadline"


class DeadlineState(StrEnum):
    none = "none"
    upcoming = "upcoming"
    soon = "soon"
    today = "today"
    packaged = "packaged"
    overdue = "overdue"


# Состояния, которые список проектов показывает до срока.
_AHEAD_STATES = frozenset({DeadlineState.upcoming, DeadlineState.soon, DeadlineState.today})


class BadDeadlineError(ValueError):
    """Срок не разобрать: не ISO 8601, без пояса или раньше 2000 года. Код ответа `bad_deadline`."""

    code = BAD_DEADLINE


def parse_deadline(raw: object) -> datetime:
    """Момент срока из ISO 8601 с поясом; хранится и показывается по Москве."""
    message = localized_error(
        "Срок: дата и время в формате ISO 8601 с часовым поясом, например 2026-11-15T23:59:00+03:00",
        "Deadline: an ISO 8601 date and time with a time zone, e.g. 2026-11-15T23:59:00+03:00",
    )
    if not isinstance(raw, str):
        raise BadDeadlineError(message)
    try:
        moment = datetime.fromisoformat(raw.strip())
    except ValueError:
        raise BadDeadlineError(message) from None
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise BadDeadlineError(message)
    if moment.year < MIN_YEAR:
        raise BadDeadlineError(
            localized_error(f"Срок раньше {MIN_YEAR} года", f"The deadline is before the year {MIN_YEAR}")
        )
    return moment.astimezone(DISPLAY_ZONE)


def packaged_at(deadline: datetime, built: Iterable[datetime]) -> datetime | None:
    """Последняя сборка пакета точки к сроку: за `PACKAGE_WINDOW` до срока и не позже него."""
    window = [moment for moment in built if deadline - PACKAGE_WINDOW <= moment <= deadline]
    return max(window, default=None)


def deadline_state(deadline: datetime | None, *, now: datetime, packaged: datetime | None) -> DeadlineState:
    """Состояние срока точки (16.6); `packaged` это `packaged_at` этого срока."""
    if deadline is None:
        return DeadlineState.none
    if now > deadline:
        return DeadlineState.packaged if packaged is not None else DeadlineState.overdue
    days = (deadline.astimezone(DISPLAY_ZONE).date() - now.astimezone(DISPLAY_ZONE).date()).days
    if days <= 0:
        return DeadlineState.today
    return DeadlineState.soon if days <= SOON_DAYS else DeadlineState.upcoming


def route_deadline_from_point(point: datetime | None, *, now: datetime) -> datetime | None:
    """Срок нового черновика маршрута из срока точки (16.5): на сутки раньше в то же время по Москве; если до срока
    точки меньше двух суток, ровно срок точки; срок точки прошёл или его нет, значит срока маршрута нет."""
    if point is None or point <= now:
        return None
    moment = point.astimezone(DISPLAY_ZONE)
    return moment if moment - now < ROUTE_MARGIN_MIN else moment - ROUTE_MARGIN


def reminder_due(deadline: datetime, *, now: datetime, packaged: datetime | None, days: int = REMINDER_DAYS) -> bool:
    """Пора ли напомнить автору о сроке точки (16.7): за `days` суток до срока и до него самого, пока пакет точки
    к сроку не собран. После срока напоминаний нет, `days <= 0` их выключает."""
    if days <= 0 or packaged is not None:
        return False
    return deadline - timedelta(days=days) <= now < deadline


def reminder_key(project_id: UUID, profile_id: str, deadline: datetime) -> str:
    """Ключ повтора напоминания `checkpoint:<проект>:<точка>:<срок>:due`: одно на срок, новый срок даёт новое.

    Срок в ключе это момент в секундах UTC, поэтому тот же срок в другом поясе ключ не меняет. Слишком длинный id
    точки заменяется отпечатком, чтобы ключ влез в колонку.
    """
    moment = int(deadline.timestamp())
    key = f"checkpoint:{project_id.hex}:{profile_id}:{moment}:due"
    if len(key) <= _KEY_MAX:
        return key
    digest = hashlib.sha256(profile_id.encode()).hexdigest()[:16]
    return f"checkpoint:{project_id.hex}:#{digest}:{moment}:due"


@dataclass(frozen=True)
class CheckpointDeadline:
    """Срок точки и его состояние: ответ `PUT .../deadline`, поля профиля сдачи и MCP."""

    profile_id: str
    deadline: datetime | None
    state: DeadlineState
    packaged_at: datetime | None


def checkpoint_deadline(
    profile_id: str, deadline: datetime | None, built: Iterable[datetime], *, now: datetime
) -> CheckpointDeadline:
    """Срок точки по моментам сборки её пакетов (`built`: время записей сдачи этой точки)."""
    packaged = packaged_at(deadline, built) if deadline is not None else None
    return CheckpointDeadline(
        profile_id=profile_id,
        deadline=deadline,
        state=deadline_state(deadline, now=now, packaged=packaged),
        packaged_at=packaged,
    )


@dataclass(frozen=True)
class NextDeadline:
    """Ближайший срок проекта для списка проектов (16.6): точка с названием из пака."""

    profile_id: str
    name: Mapping[str, str]
    deadline: datetime
    state: DeadlineState


def next_deadline(
    deadlines: Iterable[CheckpointDeadline], names: Mapping[str, Mapping[str, str]], *, now: datetime
) -> NextDeadline | None:
    """Один срок на проект: ближайший до срока в пределах `LIST_AHEAD`, иначе самая свежая просрочка не старше
    `LIST_OVERDUE`. «Пакет собран» и старые просрочки список не показывает. Точки без названия (их нет в версии
    шаблона) не берутся."""
    known = [d for d in deadlines if d.deadline is not None and d.profile_id in names]
    ahead = [d for d in known if d.state in _AHEAD_STATES and d.deadline is not None and d.deadline <= now + LIST_AHEAD]
    late = [
        d
        for d in known
        if d.state is DeadlineState.overdue and d.deadline is not None and now - d.deadline <= LIST_OVERDUE
    ]
    if ahead:
        pick = min(ahead, key=lambda d: d.deadline or now)
    elif late:
        pick = max(late, key=lambda d: d.deadline or now)
    else:
        return None
    assert pick.deadline is not None  # noqa: S101 — отобраны только сроки с датой
    return NextDeadline(
        profile_id=pick.profile_id, name=dict(names[pick.profile_id]), deadline=pick.deadline, state=pick.state
    )


# Конкретные даты в подсказке пака (16.4): те же правила, что у линтера справки (`scripts/docs/lint_docs.py`),
# и сверх них день с месяцем числами («15.11») и английский день перед месяцем («15 November»).
_MONTHS_RU = r"(январ|феврал|март|апрел|ма[йя]|июн|июл|август|сентябр|октябр|ноябр|декабр)"
_MONTHS_EN = r"(January|February|March|April|May|June|July|August|September|October|November|December)"
DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\b\d{{1,2}}\s+{_MONTHS_RU}", re.IGNORECASE),
    # «15.11» и «15.11.2026», но не номер версии «2026.1.4».
    re.compile(r"(?<![\d.])\d{1,2}\.\d{1,2}(?:\.\d{2,4})?(?!\.?\d)"),
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    re.compile(rf"\b{_MONTHS_EN}\s+\d{{1,2}}\b", re.IGNORECASE),
    re.compile(rf"\b\d{{1,2}}(st|nd|rd|th)?\s+{_MONTHS_EN}\b", re.IGNORECASE),
)


def has_date(text: str) -> bool:
    return any(pattern.search(text) for pattern in DATE_PATTERNS)


def parse_deadline_hint(raw: object) -> dict[str, str] | None:
    """Подсказка срока точки из пака: `{ru, en}`. `ValueError`, если она битая (16.4), None, если её нет.

    Битая это не словарь, нет одной из локалей, текст пустой, длиннее `HINT_MAX_LEN` или с конкретной датой: сроки
    меняются каждый год, а выпущенная версия пака неизменна.
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise TypeError("deadline_hint must be a mapping {ru, en}")
    hint: dict[str, str] = {}
    for lang in HINT_LANGS:
        text = raw.get(lang)
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"deadline_hint.{lang} is missing")
        text = text.strip()
        if len(text) > HINT_MAX_LEN:
            raise ValueError(f"deadline_hint.{lang} is longer than {HINT_MAX_LEN} characters")
        if has_date(text):
            raise ValueError(f"deadline_hint.{lang} names a concrete date: deadlines change every year")
        hint[lang] = text
    return hint


def project_next_deadline(
    deadlines: Mapping[str, datetime],
    names: Mapping[str, Mapping[str, str]],
    built: Mapping[str, Iterable[datetime]],
    *,
    now: datetime,
) -> NextDeadline | None:
    """Ближайший срок проекта по срокам точек, их названиям в версии шаблона и сборкам пакетов (`built` по точкам)."""
    states = [
        checkpoint_deadline(profile_id, moment, built.get(profile_id, ()), now=now)
        for profile_id, moment in deadlines.items()
    ]
    return next_deadline(states, names, now=now)


# Сборки пакетов, которые нужны списку проектов: просрочка не старше `LIST_OVERDUE` и окно сборки к её сроку.
LIST_BUILT_SINCE = LIST_OVERDUE + PACKAGE_WINDOW
