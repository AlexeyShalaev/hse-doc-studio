"""Таблица 5.5: что сбрасывает маршрут, и уход участника (раздел 5.4)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.enums import DetachedVerdict, SignMode
from hse_doc_studio.core.signing_route.effects import Notify, Withhold
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    Notice,
    ParticipantState,
    RoutePhase,
    RouteStatus,
    StopReason,
)
from hse_doc_studio.core.signing_route.transitions import apply_evaluation

from tests.unit.core.signing_route.world import (
    DOC,
    DOC2,
    T0,
    Driver,
    World,
    by_persona,
    make_route,
    participant,
    signer,
)

_PERSONAS = ("author", "supervisor", "academic_supervisor")


def _images_route() -> Driver:
    """Все картинкой; автор отправил, научрук согласовал, ждём академрука."""
    world = World(modes=dict.fromkeys(_PERSONAS, SignMode.image), docs=(DOC, DOC2))
    people = [participant(step, persona, [persona]) for step, persona in enumerate(_PERSONAS, start=1)]
    driver = Driver(world, make_route(people))
    author, supervisor = people[0], people[1]
    assert author.user_id is not None
    driver.send(by=author.user_id)
    driver.act(supervisor.id)
    return driver


def _signed_route() -> Driver:
    """Все ЭП с известными ключами, маршрут завершён: документы зафиксированы и подписаны."""
    world = World(modes=dict.fromkeys(_PERSONAS, SignMode.detached_text))
    people = [participant(step, persona, [persona]) for step, persona in enumerate(_PERSONAS, start=1)]
    for p in people:
        assert p.user_id is not None
        world.plates[p.user_id] = signer(p.persona)
    driver = Driver(world, make_route(people))
    assert people[0].user_id is not None
    driver.send(by=people[0].user_id)
    driver.run()
    assert driver.route.status is RouteStatus.completed
    return driver


def test__evaluate__route_doc_rebuilt__paused_rebuilt() -> None:
    driver = _images_route()
    driver.world.compiled[DOC] = "c" * 64

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop) == (RouteStatus.paused, StopReason.rebuilt)


def test__evaluate__route_doc_rebuilt__withholds_images_again() -> None:
    driver = _images_route()
    driver.world.compiled[DOC] = "c" * 64

    evaluation = driver.evaluate()

    assert set(evaluation.effects) >= {Withhold(DOC, "author"), Withhold(DOC, "supervisor")}


def test__evaluate__route_doc_rebuilt__notifies_sender_and_who_approved() -> None:
    driver = _images_route()
    people = by_persona(driver.route)
    driver.world.compiled[DOC] = "c" * 64

    evaluation = driver.evaluate()

    notices = [e for e in evaluation.effects if isinstance(e, Notify)]
    assert notices == [Notify(Notice.paused, (people["author"].id, people["supervisor"].id), sender=True)]


def test__evaluate__completed_route_doc_rebuilt__paused() -> None:
    driver = _signed_route()
    driver.world.compiled[DOC] = "c" * 64

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop) == (RouteStatus.paused, StopReason.rebuilt)


@pytest.mark.parametrize("removed", [False, True], ids=["другой", "удалён"])
def test__evaluate__frozen_pdf_changed_outside_route__paused_frozen_changed(removed: bool) -> None:
    driver = _signed_route()
    if removed:
        del driver.world.frozen[DOC]
    else:
        driver.world.frozen[DOC] = replace(driver.world.frozen[DOC], sha256="f" * 64)

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop) == (RouteStatus.paused, StopReason.frozen_changed)


def test__evaluate__visible_layer_changed_outside_route__paused_marks_changed() -> None:
    driver = _images_route()
    driver.world.slots["author"] = replace(driver.world.slots["author"], png_path="other.png")

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop) == (RouteStatus.paused, StopReason.marks_changed)


@pytest.mark.parametrize("invalid", [False, True], ids=["удалена", "недействительна"])
def test__evaluate__signature_of_completed_route_lost__only_that_slot_waits_again(invalid: bool) -> None:
    driver = _signed_route()
    supervisor = by_persona(driver.route)["supervisor"]
    pair = DocSlot(DOC, "supervisor")
    if invalid:
        sig = driver.world.detached[DOC]["supervisor"]
        driver.world.detached[DOC]["supervisor"] = replace(sig, verdict=DetachedVerdict.invalid)
    else:
        driver.world.unsign(pair)

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.phase, evaluation.stop) == (RouteStatus.active, RoutePhase.signing, None)
    states = {v.participant_id: v.state for v in evaluation.participants}
    assert states.pop(supervisor.id) is ParticipantState.to_sign
    assert set(states.values()) == {ParticipantState.done}


def test__evaluate__signature_lost_in_active_route__no_stop_and_no_refreeze() -> None:
    world = World(modes=dict.fromkeys(_PERSONAS, SignMode.detached_text))
    people = [participant(step, persona, [persona]) for step, persona in enumerate(_PERSONAS, start=1)]
    for p in people:
        assert p.user_id is not None
        world.plates[p.user_id] = signer(p.persona)
    driver = Driver(world, make_route(people))
    assert people[0].user_id is not None
    driver.send(by=people[0].user_id)
    driver.act(people[0].id)
    world.unsign(DocSlot(DOC, "author"))

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop, evaluation.effects) == (RouteStatus.active, None, ())
    assert evaluation.participant(people[0].id).state is ParticipantState.to_sign


def test__evaluate__other_documents_rebuilt_or_restamped__nothing() -> None:
    driver = _images_route()
    driver.world.compiled[DOC2] = "c" * 64
    driver.world.withheld[DOC2].add("author")

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop, evaluation.effects) == (RouteStatus.active, None, ())


def test__evaluate__participant_lost_persona__paused_participant_left() -> None:
    driver = _images_route()
    people = by_persona(driver.route)
    driver.world.personas = {
        p.user_id: frozenset({p.persona})
        for p in people.values()
        if p.user_id is not None and p.persona != "supervisor"
    }

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop) == (RouteStatus.paused, StopReason.participant_left)
    assert evaluation.stopped_by == people["supervisor"].id


def test__evaluate__members_unknown__does_not_check_who_left() -> None:
    driver = _images_route()
    driver.world.personas = None

    evaluation = driver.evaluate()

    assert evaluation.stop is None


def test__apply_evaluation__stop__route_paused_with_reason() -> None:
    driver = _images_route()
    driver.world.compiled[DOC] = "c" * 64

    route = apply_evaluation(driver.route, driver.evaluate(), at=T0)

    assert (route.status, route.phase, route.stop_reason) == (RouteStatus.paused, None, StopReason.rebuilt)


def test__evaluate__paused_route_same_facts__no_more_effects() -> None:
    driver = _images_route()
    driver.world.compiled[DOC] = "c" * 64
    driver.settle()

    evaluation = evaluate(driver.route, driver.world.facts())

    assert (evaluation.status, evaluation.effects) == (RouteStatus.paused, ())


def test__evaluate__participant_left__only_sender_is_notified() -> None:
    driver = _images_route()
    people = by_persona(driver.route)
    driver.world.personas = {
        p.user_id: frozenset({p.persona})
        for p in people.values()
        if p.user_id is not None and p.persona != "supervisor"
    }

    evaluation = driver.evaluate()

    assert [e for e in evaluation.effects if isinstance(e, Notify)] == [Notify(Notice.paused, sender=True)]


def test__evaluate__completed_route_participant_left__stays_completed() -> None:
    driver = _signed_route()
    driver.world.personas = {}

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop) == (RouteStatus.completed, None)
