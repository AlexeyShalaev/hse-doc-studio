"""Правила напоминаний маршрута (docs/design/signing-route.md, раздел 5.7): чистые функции."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.entities import EventKind, Participant, RouteEvent, SigningRoute
from hse_doc_studio.core.signing_route.reminders import (
    REMIND_INTERVAL,
    ReminderPolicy,
    ReminderTrigger,
    auto_reminders,
    due_reminder,
    last_contact,
    mark_reminded,
    may_be_due,
    remind_available_at,
    reminder_event,
)

from tests.unit.core.signing_route.world import Driver, World, make_route, participant

POLICY = ReminderPolicy()
_D = ReminderTrigger.deadline
_W = ReminderTrigger.waiting


def _sent() -> tuple[SigningRoute, Participant, datetime]:
    """Автор отправил маршрут; очередь научрука. Возвращает маршрут, научрука и время запроса ему."""
    driver = Driver(
        World({"author": SignMode.image, "supervisor": SignMode.image}),
        make_route([participant(1, "author", ["author"]), participant(2, "supervisor", ["supervisor"])]),
    )
    author, supervisor = driver.route.participants
    assert author.user_id is not None
    driver.send(author.user_id)
    asked = driver.route.participant(supervisor.id)
    assert asked.notified is not None
    return driver.route, asked, asked.notified.at


def test__last_contact__request_of_this_round_then_later_reminder() -> None:
    route, supervisor, asked = _sent()

    assert last_contact(route, supervisor) == asked
    reminded = mark_reminded(route, supervisor.id, at=asked + timedelta(hours=20))
    assert last_contact(reminded, reminded.participant(supervisor.id)) == asked + timedelta(hours=20)


def test__no_request_this_round__nothing_to_remind_about_automatically() -> None:
    route, supervisor, asked = _sent()
    assert supervisor.notified is not None
    stale = replace(supervisor, notified=replace(supervisor.notified, round=route.round - 1))
    author = route.participants[0]  # согласовал отправкой, запроса ему не было

    assert last_contact(route, stale) is None
    assert last_contact(route, author) is None
    assert due_reminder(route, stale, (), POLICY, now=asked + timedelta(days=30)) is None
    assert not may_be_due(route.with_participant(stale), POLICY, now=asked + timedelta(days=30))


def test__mark_reminded__sets_time_and_counts() -> None:
    route, supervisor, asked = _sent()

    once = mark_reminded(route, supervisor.id, at=asked + timedelta(hours=1))
    twice = mark_reminded(once, supervisor.id, at=asked + timedelta(hours=14))

    marked = twice.participant(supervisor.id)
    assert (marked.reminded_at, marked.reminders) == (asked + timedelta(hours=14), 2)
    assert remind_available_at(marked) == asked + timedelta(hours=14) + REMIND_INTERVAL
    assert remind_available_at(supervisor) is None


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (timedelta(days=2, hours=23), None),
        (timedelta(days=3), _W),
        (timedelta(days=10), _W),
    ],
)
def test__due_reminder__no_deadline__after_three_days_of_silence(
    after: timedelta, expected: ReminderTrigger | None
) -> None:
    route, supervisor, asked = _sent()

    assert due_reminder(route, supervisor, (), POLICY, now=asked + after) is expected


def test__due_reminder__manual_reminder_moves_waiting_clock() -> None:
    route, supervisor, asked = _sent()
    route = mark_reminded(route, supervisor.id, at=asked + timedelta(days=2))
    reminded = route.participant(supervisor.id)

    assert due_reminder(route, reminded, (), POLICY, now=asked + timedelta(days=4)) is None
    assert due_reminder(route, reminded, (), POLICY, now=asked + timedelta(days=5)) is _W


@pytest.mark.parametrize(
    ("deadline_in", "after", "expected"),
    [
        (timedelta(days=2), timedelta(hours=23), None),  # до срока больше суток
        (timedelta(days=2), timedelta(days=1), _D),  # ровно сутки до срока
        (timedelta(days=2), timedelta(days=1, hours=23), _D),
        (timedelta(days=2), timedelta(days=2), None),  # срок прошёл: о сроке больше не напоминаем
        (timedelta(hours=18), timedelta(hours=6), None),  # запрос был меньше 12 часов назад
        (timedelta(hours=18), timedelta(hours=12), _D),
        (timedelta(hours=6), timedelta(hours=12), None),  # срок прошёл раньше, чем кончилась тишина
        (timedelta(days=2), timedelta(days=3), _W),  # просрочено, зато три дня тишины
    ],
)
def test__due_reminder__deadline__one_day_before_but_not_right_after_request(
    deadline_in: timedelta, after: timedelta, expected: ReminderTrigger | None
) -> None:
    route, supervisor, asked = _sent()
    route = replace(route, deadline=asked + deadline_in)

    assert due_reminder(route, supervisor, (), POLICY, now=asked + after) is expected


def test__due_reminder__deadline_only_once_per_round_and_at_most_three() -> None:
    route, supervisor, asked = _sent()
    route = replace(route, deadline=asked + timedelta(days=5))
    now = asked + timedelta(days=4, hours=6)

    assert due_reminder(route, supervisor, (), POLICY, now=now) is _D
    assert due_reminder(route, supervisor, (_D,), POLICY, now=now) is _W
    assert due_reminder(route, supervisor, (_W, _D, _W), POLICY, now=now) is None
    assert due_reminder(route, supervisor, (), replace(POLICY, max_auto=0), now=now) is None


def test__due_reminder__invited_without_account__never() -> None:
    route, supervisor, asked = _sent()
    invited = replace(supervisor, user_id=None, invitation_id="inv_x")

    assert due_reminder(route, invited, (), POLICY, now=asked + timedelta(days=30)) is None


def test__may_be_due__rough_check_by_time_only() -> None:
    route, _, asked = _sent()

    assert not may_be_due(route, POLICY, now=asked + timedelta(days=1))
    assert may_be_due(route, POLICY, now=asked + timedelta(days=3))
    assert not may_be_due(route, replace(POLICY, max_auto=0), now=asked + timedelta(days=3))


def test__auto_reminders__only_automatic_of_this_round_per_participant() -> None:
    route, supervisor, asked = _sent()
    other = route.participants[0]
    events = [
        reminder_event(route, supervisor.id, ReminderTrigger.manual, at=asked, actor_id=other.user_id),
        reminder_event(route, supervisor.id, _D, at=asked),
        reminder_event(route, supervisor.id, _W, at=asked),
        reminder_event(route, other.id, _W, at=asked),
        replace(reminder_event(route, supervisor.id, _W, at=asked), round=route.round - 1),
        RouteEvent(route.id, route.round, asked, EventKind.sent, other.user_id),
    ]

    assert auto_reminders(route, events) == {supervisor.id: (_D, _W), other.id: (_W,)}


def test__reminder_event__history_row_with_trigger_and_delivery() -> None:
    route, supervisor, asked = _sent()
    actor = route.participants[0].user_id

    manual = reminder_event(route, supervisor.id, ReminderTrigger.manual, at=asked, actor_id=actor, delivery="email")
    auto = reminder_event(route, supervisor.id, _W, at=asked)

    assert (manual.kind, manual.round, manual.actor_id, manual.participant_id) == (
        EventKind.reminded,
        route.round,
        actor,
        supervisor.id,
    )
    assert manual.details == {"trigger": "manual", "delivery": "email"}
    assert (auto.actor_id, auto.details) == (None, {"trigger": "waiting"})
