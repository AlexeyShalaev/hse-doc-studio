"""Таблица 12.5: маршрут подписывает версию на подписи, правка и пересборка его не останавливают."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.engine import RouteFacts, evaluate
from hse_doc_studio.core.signing_route.entities import DocSlot, RouteStatus, StopReason
from hse_doc_studio.core.signing_route.signer import changed_docs

from tests.unit.core.signing_route.world import DOC, DOC2, Driver, World, make_route, participant, signer

_PERSONAS = ("author", "supervisor", "academic_supervisor")


def _route(mode: SignMode, *, finish: bool) -> Driver:
    """Два документа, у каждого участника слот на обоих. `finish`: довести маршрут до завершения."""
    world = World(modes=dict.fromkeys(_PERSONAS, mode), docs=(DOC, DOC2))
    people = [participant(step, persona, [persona], docs=(DOC, DOC2)) for step, persona in enumerate(_PERSONAS, 1)]
    for p in people:
        assert p.user_id is not None
        world.plates[p.user_id] = signer(p.persona)
    driver = Driver(world, make_route(people, docs=(DOC, DOC2)))
    assert people[0].user_id is not None
    driver.send(by=people[0].user_id)
    if finish:
        driver.run()
        assert driver.route.status is RouteStatus.completed
    else:
        driver.act(people[1].id)
        assert driver.route.status is RouteStatus.active
    return driver


_ROUTES = [
    pytest.param(SignMode.image, False, id="идёт, картинки"),
    pytest.param(SignMode.detached_text, True, id="завершён, ЭП"),
]


@pytest.mark.parametrize(("mode", "finish"), _ROUTES)
def test__evaluate__document_rebuilt_after_send__route_goes_on_with_working_build_ahead(
    mode: SignMode, finish: bool
) -> None:
    driver = _route(mode, finish=finish)
    status = driver.route.status
    driver.world.compiled[DOC] = "c" * 64

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop, evaluation.effects) == (status, None, ())
    facts = driver.world.facts()
    assert facts.doc(DOC).working_differs
    assert not facts.doc(DOC2).working_differs
    assert changed_docs(driver.route, facts) == ()


def test__evaluate__every_document_rebuilt_and_unbuilt__completed_route_stays_completed() -> None:
    driver = _route(SignMode.detached_text, finish=True)
    driver.world.compiled[DOC] = "c" * 64
    driver.world.compiled[DOC2] = None

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop, evaluation.effects) == (RouteStatus.completed, None, ())


def _replaced(world: World) -> None:
    world.pinned[DOC] = "d" * 64


def _unpinned(world: World) -> None:
    world.compiled[DOC] = "c" * 64
    del world.pinned[DOC]


def _file_lost(world: World) -> None:
    world.pinned[DOC] = None


def _without_doc(facts: RouteFacts) -> RouteFacts:
    return replace(facts, docs={doc_id: doc for doc_id, doc in facts.docs.items() if doc_id != DOC})


_SENT_CHANGES = [
    pytest.param(_replaced, id="версия на подписи другая"),
    pytest.param(_unpinned, id="запись версии на подписи снята"),
    pytest.param(_file_lost, id="файл версии на подписи удалён"),
]


@pytest.mark.parametrize("change", _SENT_CHANGES)
@pytest.mark.parametrize(("mode", "finish"), _ROUTES)
def test__evaluate__pinned_version_changed_outside_route__paused_sent_changed(
    change: Callable[[World], None], mode: SignMode, finish: bool
) -> None:
    driver = _route(mode, finish=finish)
    change(driver.world)

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop) == (RouteStatus.paused, StopReason.sent_changed)
    assert changed_docs(driver.route, driver.world.facts()) == (DOC,)


@pytest.mark.parametrize(("mode", "finish"), _ROUTES)
def test__evaluate__document_gone_from_project__paused_sent_changed(mode: SignMode, finish: bool) -> None:
    driver = _route(mode, finish=finish)

    evaluation = evaluate(driver.route, _without_doc(driver.world.facts()))

    assert (evaluation.status, evaluation.stop) == (RouteStatus.paused, StopReason.sent_changed)


def test__evaluate__unpinned_but_build_has_the_same_bytes__nothing_to_stop() -> None:
    driver = _route(SignMode.image, finish=False)
    del driver.world.pinned[DOC]

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop, evaluation.effects) == (RouteStatus.active, None, ())


@pytest.mark.parametrize(
    "change",
    [
        pytest.param(lambda w: w.compiled.__setitem__(DOC, "c" * 64), id="пересборка"),
        pytest.param(lambda w: w.pinned.__setitem__(DOC, "d" * 64), id="версия на подписи"),
        pytest.param(lambda w: w.frozen.pop(DOC), id="B удалён"),
        pytest.param(lambda w: w.unsign(DocSlot(DOC, "author")), id="ЭП удалена"),
    ],
)
def test__evaluate__any_change__never_stops_with_rebuilt(change: Callable[[World], object]) -> None:
    driver = _route(SignMode.detached_text, finish=True)
    change(driver.world)

    assert driver.evaluate().stop is not StopReason.rebuilt


def test__evaluate__route_stopped_on_0_20_0_with_rebuilt__stays_paused_with_its_reason() -> None:
    driver = _route(SignMode.image, finish=False)
    driver.route = replace(driver.route, status=RouteStatus.paused, phase=None, stop_reason=StopReason.rebuilt)

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop) == (RouteStatus.paused, None)
    assert driver.route.stop_reason is StopReason.rebuilt
