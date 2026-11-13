"""Состояние подписания точки в напоминании о сроке (docs/design/signing-route.md, 16.7).

Маршрут «автор, научрук, академрук» картинками: после отправки очередь научрука. Расчёт на текущих фактах.
"""

from __future__ import annotations

from dataclasses import replace

from hse_doc_studio.core.checkpoint_reminders import AwaitedSigner, CheckpointSigning, SigningState
from hse_doc_studio.core.signing_route.entities import RouteStatus
from hse_doc_studio.core.signing_route.transitions import archive, cancel
from hse_doc_studio.use_cases.signing_route.checkpoint_signing import CheckpointSigningReader

from tests.fakes.signing_routes import InMemorySigningRouteRepository, StaticRouteContext
from tests.unit.core.signing_route.world import Driver
from tests.unit.use_cases.signing_route.helpers import context, people, three_steps


async def _read(driver: Driver, *, facts: StaticRouteContext | None = None) -> CheckpointSigning | None:
    routes = InMemorySigningRouteRepository()
    await routes.add(driver.route)
    reader = CheckpointSigningReader(routes, facts or context(driver), people(driver.route))
    return await reader.signing(driver.route.project_id, driver.route.profile_id)


def _sent() -> Driver:
    driver = three_steps()
    author = driver.route.participants[0]
    assert author.user_id is not None
    driver.send(author.user_id)
    return driver


async def test__no_route__none() -> None:
    driver = three_steps()
    reader = CheckpointSigningReader(InMemorySigningRouteRepository(), context(driver), people(driver.route))

    assert await reader.signing(driver.route.project_id, driver.route.profile_id) is None


async def test__going_route__waits_for_whose_turn_it_is_by_role_and_name() -> None:
    signing = await _read(_sent())

    assert signing == CheckpointSigning(SigningState.waiting, (AwaitedSigner("supervisor", "Пётр"),))
    assert signing.whom("ru") == "научного руководителя (Пётр)"
    assert signing.whom("en") == "the supervisor (Пётр)"


async def test__everyone_signed__completed() -> None:
    driver = _sent()
    driver.run()
    assert driver.route.status is RouteStatus.completed

    assert await _read(driver) == CheckpointSigning(SigningState.completed)


async def test__draft_or_cancelled__not_sent() -> None:
    cancelled = _sent()
    cancelled.route = cancel(cancelled.route)

    assert await _read(three_steps()) == CheckpointSigning(SigningState.not_sent)
    assert await _read(cancelled) == CheckpointSigning(SigningState.not_sent)


async def test__archived_route__not_counted() -> None:
    driver = _sent()
    driver.route = archive(cancel(driver.route))

    assert await _read(driver) is None


async def test__going_by_status_but_stopped_by_facts__not_sent() -> None:
    driver = _sent()
    # Документ маршрута пропал из проекта: по расчёту маршрут уже остановлен, сверка ещё не записала.
    stopped = StaticRouteContext(facts_of=lambda _route: replace(driver.world.facts(), docs={}))

    assert await _read(driver, facts=stopped) == CheckpointSigning(SigningState.not_sent)


async def test__project_unreadable__by_stored_status_without_names() -> None:
    signing = await _read(_sent(), facts=StaticRouteContext())

    assert signing == CheckpointSigning(SigningState.waiting)
    assert signing.whom("ru") is None
