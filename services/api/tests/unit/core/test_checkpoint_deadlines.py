"""Сроки контрольных точек (docs/design/signing-route.md, 16.4 и 16.6): разбор, состояние, ближайший срок, подсказка."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hse_doc_studio.core.checkpoint_deadlines import (
    BadDeadlineError,
    DeadlineState,
    checkpoint_deadline,
    deadline_state,
    has_date,
    next_deadline,
    packaged_at,
    parse_deadline,
    parse_deadline_hint,
    project_next_deadline,
)

pytestmark = pytest.mark.unit

MSK = timezone(timedelta(hours=3))
# Срок по умолчанию в интерфейсе: 23:59 по Москве.
DEADLINE = datetime(2026, 11, 15, 23, 59, tzinfo=MSK)
NAMES = {"topic-approval": {"ru": "Заявка на тему", "en": "Topic application"}, "final": {"ru": "Итог", "en": "Final"}}


def _msk(day: int, hour: int, minute: int = 0, month: int = 11) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=MSK)


# --- разбор ------------------------------------------------------------------------------------


def test__parse_deadline__iso_with_zone__moscow_moment() -> None:
    parsed = parse_deadline("2026-11-15T20:59:00Z")

    assert parsed == DEADLINE
    assert parsed.utcoffset() == timedelta(hours=3)
    assert parse_deadline(" 2026-11-15T23:59:00+03:00 ") == DEADLINE


@pytest.mark.parametrize("raw", ["2026-11-15T23:59:00", "2026-11-15", "15.11.2026", "завтра", "", 5, None])
def test__parse_deadline__no_zone_or_not_iso__bad_deadline(raw: object) -> None:
    with pytest.raises(BadDeadlineError) as caught:
        parse_deadline(raw)

    assert caught.value.code == "bad_deadline"


def test__parse_deadline__before_2000__bad_deadline() -> None:
    with pytest.raises(BadDeadlineError):
        parse_deadline("1999-12-31T23:59:00+03:00")


def test__parse_deadline__in_the_past__accepted() -> None:
    """Срок задним числом ставят, чтобы видеть «просрочено» (16.8)."""
    assert parse_deadline("2001-01-01T00:00:00+03:00").year == 2001


# --- состояние (16.6) ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("now", "state"),
    [
        (_msk(1, 12), DeadlineState.upcoming),
        # Четыре дня по календарю Москвы: ещё не «скоро».
        (_msk(11, 23, 59), DeadlineState.upcoming),
        (_msk(12, 0, 0), DeadlineState.soon),
        (_msk(14, 23, 59), DeadlineState.soon),
        # Граница суток по Москве, а не 24 часа до срока.
        (_msk(15, 0, 0), DeadlineState.today),
        (_msk(15, 23, 59), DeadlineState.today),
        # В UTC это ещё 14 ноября, по Москве уже день срока.
        (datetime(2026, 11, 14, 21, 30, tzinfo=UTC), DeadlineState.today),
    ],
)
def test__deadline_state__before_the_deadline__by_moscow_calendar_days(now: datetime, state: DeadlineState) -> None:
    assert deadline_state(DEADLINE, now=now, packaged=None) is state


def test__deadline_state__no_deadline__none() -> None:
    assert deadline_state(None, now=_msk(1, 12), packaged=_msk(1, 10)) is DeadlineState.none


def test__deadline_state__after_the_deadline__packaged_or_overdue() -> None:
    after = _msk(16, 0, 0)

    assert deadline_state(DEADLINE, now=after, packaged=_msk(14, 18)) is DeadlineState.packaged
    assert deadline_state(DEADLINE, now=after, packaged=None) is DeadlineState.overdue


def test__packaged_at__only_builds_within_14_days_up_to_the_deadline_count() -> None:
    draft = DEADLINE - timedelta(days=14, minutes=1)
    first = DEADLINE - timedelta(days=14)
    last = _msk(15, 23, 59)
    late = _msk(16, 0, 1)

    assert packaged_at(DEADLINE, [draft, first, late]) == first
    assert packaged_at(DEADLINE, [first, last, late]) == last
    assert packaged_at(DEADLINE, [draft, late]) is None
    assert packaged_at(DEADLINE, []) is None


def test__checkpoint_deadline__early_draft_package__still_overdue() -> None:
    """Черновой пакет за месяц до срока не в счёт: после срока это «просрочено» (16.6)."""
    view = checkpoint_deadline("topic-approval", DEADLINE, [_msk(10, 12, month=10)], now=_msk(16, 9))

    assert (view.state, view.packaged_at) == (DeadlineState.overdue, None)


def test__checkpoint_deadline__package_before_the_deadline__packaged_and_reported_before_it_passes() -> None:
    built = [_msk(14, 18)]

    assert checkpoint_deadline("topic-approval", DEADLINE, built, now=_msk(16, 9)).state is DeadlineState.packaged
    soon = checkpoint_deadline("topic-approval", DEADLINE, built, now=_msk(14, 19))
    assert (soon.state, soon.packaged_at) == (DeadlineState.soon, _msk(14, 18))


def test__checkpoint_deadline__no_deadline__none_without_packaged_at() -> None:
    view = checkpoint_deadline("final", None, [_msk(14, 18)], now=_msk(14, 19))

    assert (view.deadline, view.state, view.packaged_at) == (None, DeadlineState.none, None)


# --- ближайший срок в списке --------------------------------------------------------------------


def test__next_deadline__nearest_ahead_within_30_days() -> None:
    now = _msk(1, 12)
    deadlines = {"topic-approval": DEADLINE, "final": _msk(20, 23, 59)}

    found = project_next_deadline(deadlines, NAMES, {}, now=now)

    assert found is not None
    assert (found.profile_id, found.deadline, found.state, dict(found.name)) == (
        "topic-approval",
        DEADLINE,
        DeadlineState.upcoming,
        NAMES["topic-approval"],
    )


def test__next_deadline__ahead_beats_a_fresh_overdue() -> None:
    now = _msk(16, 12)
    deadlines = {"topic-approval": DEADLINE, "final": _msk(20, 23, 59)}

    found = project_next_deadline(deadlines, NAMES, {}, now=now)

    assert found is not None
    assert (found.profile_id, found.state) == ("final", DeadlineState.upcoming)


def test__next_deadline__overdue_up_to_7_days_then_nothing() -> None:
    deadlines = {"topic-approval": DEADLINE}

    fresh = project_next_deadline(deadlines, NAMES, {}, now=DEADLINE + timedelta(days=7))
    stale = project_next_deadline(deadlines, NAMES, {}, now=DEADLINE + timedelta(days=7, minutes=1))

    assert fresh is not None
    assert fresh.state is DeadlineState.overdue
    assert stale is None


def test__next_deadline__packaged_far_and_unknown_checkpoints_are_not_shown() -> None:
    now = _msk(16, 12)
    built = {"topic-approval": [_msk(14, 18)]}
    far = {"final": _msk(1, 23, 59, month=12) + timedelta(days=30)}

    assert project_next_deadline({"topic-approval": DEADLINE}, NAMES, built, now=now) is None
    assert project_next_deadline(far, NAMES, {}, now=now) is None
    # Точку убрали в новой версии шаблона: срок хранится, но не показывается (16.3).
    assert project_next_deadline({"gone": _msk(20, 23, 59)}, NAMES, {}, now=now) is None
    assert next_deadline([], NAMES, now=now) is None


# --- подсказка пака (16.4) ----------------------------------------------------------------------


def test__parse_deadline_hint__both_locales__trimmed() -> None:
    hint = parse_deadline_hint(
        {
            "ru": " Обычно в середине ноября, точную дату объявляют в SmartLMS ",
            "en": "Usually mid-November; the exact date is announced in SmartLMS",
        }
    )

    assert hint == {
        "ru": "Обычно в середине ноября, точную дату объявляют в SmartLMS",
        "en": "Usually mid-November; the exact date is announced in SmartLMS",
    }
    assert parse_deadline_hint(None) is None


@pytest.mark.parametrize(
    "raw",
    [
        "Обычно в середине ноября",
        {"ru": "Обычно в середине ноября"},
        {"ru": "", "en": "Usually mid-November"},
        {"ru": "х" * 201, "en": "Usually mid-November"},
        {"ru": "Жёсткий дедлайн 15 ноября 23:59", "en": "Usually mid-November"},
        {"ru": "Обычно в середине ноября", "en": "Hard deadline November 15"},
    ],
)
def test__parse_deadline_hint__broken__rejected(raw: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        parse_deadline_hint(raw)


@pytest.mark.parametrize(
    "text",
    ["до 15 ноября", "до 1 Мая", "15.11.2026.", "до 15.11", "2026-11-15", "November 15", "15 November", "1st June"],
)
def test__has_date__concrete_dates(text: str) -> None:
    assert has_date(text)


@pytest.mark.parametrize(
    "text",
    [
        "Обычно в середине ноября, точную дату объявляют в SmartLMS",
        "За три-четыре недели до защит, дату объявляет учебный офис",
        "Usually in January; the date is announced at the mentor seminar",
        "Usually in June: the text goes to the supervisor first, then to SmartLMS; the dates are announced in SmartLMS",
        "Пак 2026.1.4",
    ],
)
def test__has_date__hints_without_dates(text: str) -> None:
    assert not has_date(text)
