"""Напоминания подписантам маршрута (docs/design/signing-route.md, раздел 5.7): чистые правила.

- «Напомнить» у автора: тому, чья очередь, не чаще раза в 12 часов на человека (`REMIND_INTERVAL`). Интервал
  считается от любого напоминания, ручного или автоматического: кнопка у автора закрыта по `reminded_at`.
- Автоматически: за сутки до срока (один раз за раунд) и после трёх суток тишины в очереди, не больше трёх
  автонапоминаний на человека за раунд (`ReminderPolicy`). Тишина это время от последнего запроса или
  напоминания, поэтому ручное «Напомнить» отодвигает автоматическое. Автонапоминание не приходит раньше чем
  через `REMIND_INTERVAL` после запроса или прошлого напоминания: запрос за шесть часов до срока уже называет
  срок, второе письмо следом было бы шумом.

Что уже отправлено, хранит сам маршрут: `Participant.reminded_at` и `reminders` (все напоминания раунда) и
события `reminded` с `details.trigger` (`manual`, `deadline`, `waiting`). Автонапоминания раунда считаются по
событиям, поэтому решение зависит только от записанного и после перезапуска сервера не повторяется.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signing_route.entities import (
    TURN_STATES,
    EventKind,
    Participant,
    ParticipantState,
    RouteConflictError,
    RouteEvent,
    SigningRoute,
)

# Ручное «Напомнить»: не чаще раза за это время на человека. То же число держит фронтенд (`REMIND_INTERVAL_MS`).
REMIND_INTERVAL = timedelta(hours=12)
# Кому автор может напомнить: чья очередь, и приглашённому (ему повторяется приглашение, раздел 6.5).
REMINDABLE_STATES = TURN_STATES | {ParticipantState.invited}


class ReminderTrigger(StrEnum):
    """Почему ушло напоминание: `details.trigger` события `reminded`."""

    manual = "manual"  # «Напомнить» у автора
    deadline = "deadline"  # до срока маршрута осталось меньше суток
    waiting = "waiting"  # участник давно в очереди, и ему давно не писали


AUTO_TRIGGERS = frozenset({ReminderTrigger.deadline, ReminderTrigger.waiting})


@dataclass(frozen=True)
class ReminderPolicy:
    """Правила автонапоминаний. `max_auto` 0 выключает их."""

    before_deadline: timedelta = timedelta(days=1)
    waiting: timedelta = timedelta(days=3)
    max_auto: int = 3
    quiet: timedelta = REMIND_INTERVAL


def not_waiting() -> RouteConflictError:
    return RouteConflictError(
        "participant_not_waiting",
        localized_error(
            "Напоминать некому: маршрут не идёт, очередь участника не настала или он уже закончил",
            "Nothing to remind about: the route is not running, it is not the participant's turn or they are done",
        ),
    )


def remind_available_at(participant: Participant) -> datetime | None:
    """Когда автору снова можно напомнить этому человеку; None, если ему ещё не напоминали."""
    if participant.reminded_at is None:
        return None
    return participant.reminded_at + REMIND_INTERVAL


def last_contact(route: SigningRoute, participant: Participant) -> datetime | None:
    """Когда участнику последний раз писали в этом раунде: запрос или напоминание.

    Запроса раунда может не быть у того, кто уже согласовал отправкой и снова в очереди; тогда отсчёт от отправки.
    """
    asked = participant.notified
    since = asked.at if asked is not None and asked.round == route.round else route.sent_at
    reminded = participant.reminded_at
    if since is None:
        return reminded
    return since if reminded is None or reminded < since else reminded


def auto_reminders(route: SigningRoute, events: Iterable[RouteEvent]) -> Mapping[UUID, tuple[ReminderTrigger, ...]]:
    """Автонапоминания текущего раунда по участникам, в порядке отправки."""
    found: dict[UUID, tuple[ReminderTrigger, ...]] = {}
    for event in events:
        if event.kind is not EventKind.reminded or event.round != route.round or event.participant_id is None:
            continue
        trigger = event.details.get("trigger")
        if isinstance(trigger, str) and trigger in AUTO_TRIGGERS:
            found[event.participant_id] = (*found.get(event.participant_id, ()), ReminderTrigger(trigger))
    return found


def due_reminder(
    route: SigningRoute,
    participant: Participant,
    sent: Iterable[ReminderTrigger],
    policy: ReminderPolicy,
    *,
    now: datetime,
) -> ReminderTrigger | None:
    """Какое автонапоминание пора отправить участнику, чья очередь; None, если никакого.

    Очередь участника проверяет вызывающий по расчёту маршрута: здесь только время и уже отправленное (`sent`,
    автонапоминания этого раунда). Приглашённому без аккаунта писать некуда.
    """
    already = tuple(sent)
    if participant.user_id is None or len(already) >= policy.max_auto:
        return None
    contact = last_contact(route, participant)
    if contact is None or now - contact < policy.quiet:
        return None
    deadline = route.deadline
    if (
        deadline is not None
        and ReminderTrigger.deadline not in already
        and deadline - policy.before_deadline <= now < deadline
    ):
        return ReminderTrigger.deadline
    if now - contact >= policy.waiting:
        return ReminderTrigger.waiting
    return None


def may_be_due(route: SigningRoute, policy: ReminderPolicy, *, now: datetime) -> bool:
    """Стоит ли читать факты и события маршрута: есть ли участник, которому по времени пора напомнить.

    Грубая проверка без расчёта и истории (как будто автонапоминаний ещё не было): отсекает маршруты, где
    напоминать заведомо рано.
    """
    if policy.max_auto <= 0:
        return False
    return any(due_reminder(route, p, (), policy, now=now) is not None for p in route.participants)


def mark_reminded(route: SigningRoute, participant_id: UUID, *, at: datetime) -> SigningRoute:
    """Запомнить напоминание участнику: время и счётчик раунда (новый раунд их обнуляет)."""
    p = route.participant(participant_id)
    return route.with_participant(replace(p, reminded_at=at, reminders=p.reminders + 1))


def reminder_event(
    route: SigningRoute,
    participant_id: UUID,
    trigger: ReminderTrigger,
    *,
    at: datetime,
    actor_id: UUID | None = None,
    delivery: str | None = None,
) -> RouteEvent:
    """Событие `reminded` истории маршрута: кто напомнил (None у сервера), кому, почему и как доставлено."""
    details: dict[str, object] = {"trigger": trigger.value}
    if delivery is not None:
        details["delivery"] = delivery
    return RouteEvent(route.id, route.round, at, EventKind.reminded, actor_id, participant_id, details)
