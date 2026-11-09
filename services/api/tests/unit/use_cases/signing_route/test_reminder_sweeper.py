"""Автонапоминания подписантам (docs/design/signing-route.md, раздел 5.7): проход периодической задачи.

Маршрут «автор, научрук, академрук» картинками: после отправки очередь научрука, академрук ждёт своего шага.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from hse_doc_studio.core.signing_route.entities import EventKind, Notice, RequestOutcome, RouteStatus, SigningRoute
from hse_doc_studio.core.signing_route.reminders import ReminderPolicy
from hse_doc_studio.core.signing_route.transitions import cancel
from hse_doc_studio.use_cases.signing_route.reminders import SigningReminderSweeper

from tests.fakes.signing_routes import InMemorySigningRouteRepository, RecordingSigningNotifier, StaticRouteContext
from tests.unit.core.signing_route.world import DOC, Driver
from tests.unit.use_cases.signing_route.helpers import context, three_steps

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

DAY = timedelta(days=1)
HOUR = timedelta(hours=1)


class _Uow:
    @asynccontextmanager
    async def begin(self) -> AsyncIterator[None]:
        yield


@dataclass
class _Stand:
    driver: Driver
    routes: InMemorySigningRouteRepository
    notifier: RecordingSigningNotifier
    facts: StaticRouteContext
    now: datetime
    policy: ReminderPolicy

    @property
    def sweeper(self) -> SigningReminderSweeper:
        """Новый объект на каждый проход: как после перезапуска сервера, память между проходами не нужна."""
        return SigningReminderSweeper(
            self.routes, self.facts, self.notifier, _Uow(), self.policy, clock=lambda: self.now
        )

    async def run_at(self, moment: datetime) -> int:
        self.now = moment
        return await self.sweeper.run()

    async def stored(self) -> SigningRoute:
        route = await self.routes.get(self.driver.route.project_id, self.driver.route.id)
        assert route is not None
        return route

    async def reminded(self) -> list[tuple[UUID | None, object, UUID | None]]:
        """События `reminded` истории: участник, причина, актор."""
        events = await self.routes.list_events(self.driver.route.id)
        return [
            (e.participant_id, e.details.get("trigger"), e.actor_id) for e in events if e.kind is EventKind.reminded
        ]


async def _stand(*, deadline_in: timedelta | None = None, policy: ReminderPolicy | None = None) -> _Stand:
    driver = three_steps()
    author = driver.route.participants[0]
    assert author.user_id is not None
    driver.send(author.user_id)
    if deadline_in is not None:
        driver.route = replace(driver.route, deadline=_asked(driver) + deadline_in)
    routes = InMemorySigningRouteRepository()
    await routes.add(driver.route)
    return _Stand(
        driver, routes, RecordingSigningNotifier(), context(driver), _asked(driver), policy or ReminderPolicy()
    )


def _asked(driver: Driver) -> datetime:
    """Когда научрук получил запрос: начало его очереди."""
    asked = driver.route.participants[1].notified
    assert asked is not None
    return asked.at


async def test__waiting_three_days__reminds_only_whose_turn_it_is() -> None:
    stand = await _stand()
    _, supervisor, academic = stand.driver.route.participants
    asked = _asked(stand.driver)

    early = await stand.run_at(asked + 2 * DAY)
    sent = await stand.run_at(asked + 3 * DAY)

    assert (early, sent) == (0, 1)
    [call] = stand.notifier.delivered
    assert [(n.notice, n.participant_ids, n.outcome) for n in call.notices] == [
        (Notice.reminder, (supervisor.id,), RequestOutcome.approve)
    ]
    assert call.actor_id is None
    route = await stand.stored()
    marked = route.participant(supervisor.id)
    assert (marked.reminded_at, marked.reminders) == (asked + 3 * DAY, 1)
    assert route.participant(academic.id).reminded_at is None  # его очередь не настала
    assert await stand.reminded() == [(supervisor.id, "waiting", None)]


async def test__same_moment_again_and_after_restart__nothing_sent_twice() -> None:
    stand = await _stand()
    asked = _asked(stand.driver)
    assert await stand.run_at(asked + 3 * DAY) == 1

    again = await stand.run_at(asked + 3 * DAY)
    later = await stand.run_at(asked + 3 * DAY + 20 * HOUR)

    assert (again, later) == (0, 0)
    assert len(stand.notifier.delivered) == 1
    assert (await stand.stored()).participants[1].reminders == 1


async def test__every_three_days__at_most_three_per_round() -> None:
    stand = await _stand()
    supervisor = stand.driver.route.participants[1]
    asked = _asked(stand.driver)

    sent = [await stand.run_at(asked + days * DAY) for days in (3, 6, 9, 12, 30)]

    assert sent == [1, 1, 1, 0, 0]
    assert await stand.reminded() == [(supervisor.id, "waiting", None)] * 3
    assert (await stand.stored()).participant(supervisor.id).reminders == 3


async def test__deadline_tomorrow__one_reminder_then_waiting_rule() -> None:
    stand = await _stand(deadline_in=5 * DAY)
    supervisor = stand.driver.route.participants[1]
    asked = _asked(stand.driver)

    before = await stand.run_at(asked + 2 * DAY)
    day_before = await stand.run_at(asked + 4 * DAY)
    same_day = await stand.run_at(asked + 4 * DAY + 13 * HOUR)
    overdue = await stand.run_at(asked + 7 * DAY)

    assert (before, day_before, same_day, overdue) == (0, 1, 0, 1)
    assert await stand.reminded() == [(supervisor.id, "deadline", None), (supervisor.id, "waiting", None)]


async def test__deadline_right_after_request__no_reminder_on_top_of_request() -> None:
    stand = await _stand(deadline_in=6 * HOUR)

    assert await stand.run_at(_asked(stand.driver) + HOUR) == 0
    assert stand.notifier.delivered == []


async def test__manual_reminder_recently__automatic_waits() -> None:
    stand = await _stand(deadline_in=4 * DAY)
    supervisor = stand.driver.route.participants[1]
    asked = _asked(stand.driver)
    route = await stand.stored()
    manual = replace(route.participant(supervisor.id), reminded_at=asked + 3 * DAY, reminders=1)
    await stand.routes.save(route.with_participant(manual))

    soon = await stand.run_at(asked + 3 * DAY + 2 * HOUR)
    later = await stand.run_at(asked + 3 * DAY + 12 * HOUR)

    assert (soon, later) == (0, 1)
    assert await stand.reminded() == [(supervisor.id, "deadline", None)]
    assert (await stand.stored()).participant(supervisor.id).reminders == 2


async def test__invited_without_account__skipped() -> None:
    stand = await _stand()
    route = await stand.stored()
    supervisor = route.participants[1]
    await stand.routes.save(route.with_participant(replace(supervisor, user_id=None, invitation_id="inv_1")))

    assert await stand.run_at(_asked(stand.driver) + 10 * DAY) == 0
    assert stand.notifier.delivered == []


async def test__document_rebuilt__route_is_about_to_pause__no_reminder() -> None:
    stand = await _stand()
    stand.driver.world.compiled[DOC] = "c" * 64

    assert await stand.run_at(_asked(stand.driver) + 5 * DAY) == 0
    assert stand.notifier.delivered == []
    assert (await stand.stored()).status is RouteStatus.active  # останавливает сверка, не напоминания


async def test__cancelled_route_and_unreadable_project__skipped_without_failure() -> None:
    stand = await _stand()
    asked = _asked(stand.driver)
    stand.facts.failing = True

    assert await stand.run_at(asked + 5 * DAY) == 0

    stand.facts.failing = False
    await stand.routes.save(cancel(await stand.stored()))
    assert await stand.run_at(asked + 5 * DAY) == 0
    assert stand.notifier.delivered == []


async def test__policy_disabled__nothing() -> None:
    stand = await _stand(policy=ReminderPolicy(max_auto=0))

    assert await stand.run_at(_asked(stand.driver) + 30 * DAY) == 0


async def test__next_step_after_approval__clock_starts_from_its_own_request() -> None:
    stand = await _stand()
    _, supervisor, academic = stand.driver.route.participants
    asked = _asked(stand.driver)
    # Научрук согласовал на третий день: академрук получил запрос только тогда.
    stand.driver.clock = asked + 3 * DAY
    stand.driver.act(supervisor.id)
    stored = await stand.stored()
    await stand.routes.save(replace(stand.driver.route, version=stored.version))
    academic_asked = stand.driver.route.participant(academic.id).notified
    assert academic_asked is not None

    early = await stand.run_at(asked + 5 * DAY)
    due = await stand.run_at(academic_asked.at + 3 * DAY)

    assert (early, due) == (0, 1)
    assert await stand.reminded() == [(academic.id, "waiting", None)]
