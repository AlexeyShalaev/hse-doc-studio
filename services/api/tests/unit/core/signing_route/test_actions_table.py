"""Таблица 4.4: граница L и число действий каждого в «Заявке на тему КП» (автор, научрук, академрук)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.effects import FillPlate, Freeze
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import NextAction, Participant, RoutePhase, RouteStatus
from hse_doc_studio.core.signing_route.transitions import send

from tests.unit.core.signing_route.world import T0, Driver, World, make_route, participant, signer

_IMAGE = SignMode.image
_EP = SignMode.detached_text
_PERSONAS = ("author", "supervisor", "academic_supervisor")


@dataclass(frozen=True)
class Case:
    modes: tuple[SignMode, SignMode, SignMode]  # автор, научрук, академрук
    known_keys: tuple[bool, bool, bool]  # данные плашки известны заранее
    last_visible_step: int  # L до отправки
    actions: tuple[int, int, int]  # нажатий после отправки: автор (подпись после отправки), научрук, академрук


_CASES = [
    pytest.param(Case((_IMAGE, _IMAGE, _IMAGE), (False, False, False), 3, (0, 1, 1)), id="все картинкой"),
    pytest.param(
        Case((_IMAGE, _EP, _EP), (False, True, True), 1, (0, 1, 1)),
        id="автор картинкой, руководители ЭП с известными ключами",
    ),
    pytest.param(Case((_EP, _EP, _EP), (True, True, True), 0, (1, 1, 1)), id="все ЭП с известными ключами"),
    pytest.param(
        Case((_EP, _EP, _IMAGE), (True, True, False), 3, (1, 2, 1)), id="автор и научрук ЭП, академрук картинкой"
    ),
    pytest.param(
        Case((_EP, _IMAGE, _EP), (True, False, False), 3, (1, 1, 1)),
        id="автор ЭП, научрук картинкой, академрук ЭП без ключа",
    ),
]


def _setup(case: Case) -> tuple[Driver, tuple[Participant, ...]]:
    world = World(modes=dict(zip(_PERSONAS, case.modes, strict=True)))
    people = tuple(participant(step, persona, [persona]) for step, persona in enumerate(_PERSONAS, start=1))
    for p, known in zip(people, case.known_keys, strict=True):
        if known and p.user_id is not None:
            world.plates[p.user_id] = signer(p.persona)
    return Driver(world, make_route(people)), people


@pytest.mark.parametrize("case", _CASES)
def test__evaluate__route_before_anyone_approved__last_visible_step_as_in_table(case: Case) -> None:
    driver, _ = _setup(case)
    sent_by_editor = send(driver.route, driver.world.facts(), by=uuid4(), at=T0)

    evaluation = evaluate(sent_by_editor, driver.world.facts())

    assert evaluation.last_visible_step == case.last_visible_step


@pytest.mark.parametrize("case", _CASES)
def test__evaluate__right_after_send__remaining_actions_as_in_table(case: Case) -> None:
    driver, people = _setup(case)
    assert people[0].user_id is not None
    driver.send(by=people[0].user_id)

    evaluation = driver.evaluate()

    assert tuple(evaluation.participant(p.id).remaining_actions for p in people) == case.actions


@pytest.mark.parametrize("case", _CASES)
def test__route__run_to_completion__each_person_acts_as_many_times_as_in_table(case: Case) -> None:
    driver, people = _setup(case)
    assert people[0].user_id is not None
    driver.send(by=people[0].user_id)

    driver.run()

    assert driver.route.status is RouteStatus.completed
    assert driver.route.phase is RoutePhase.done
    assert tuple(driver.actions[p.id] for p in people) == case.actions


@pytest.mark.parametrize("case", _CASES)
def test__route__run_to_completion__no_freeze_resets_a_placed_signature(case: Case) -> None:
    driver, people = _setup(case)
    assert people[0].user_id is not None
    driver.send(by=people[0].user_id)

    driver.run()

    assert driver.world.resets == 0
    assert all(driver.world.is_signed(pair) for p in people for pair in p.assignments if driver.world.is_crypto(pair))


def test__send__nobody_changes_visible_layer__freezes_and_sender_can_sign_at_once() -> None:
    driver, people = _setup(Case((_EP, _EP, _EP), (True, True, True), 0, (1, 1, 1)))
    assert people[0].user_id is not None

    evaluation = driver.send(by=people[0].user_id)

    assert evaluation.phase is RoutePhase.signing
    assert {type(e) for e in evaluation.effects} >= {FillPlate, Freeze}
    assert evaluation.participant(people[0].id).next_action is NextAction.sign


def test__evaluate__last_changer_with_e_signature__combines_approval_and_signing() -> None:
    driver, people = _setup(Case((_EP, _IMAGE, _EP), (True, False, False), 3, (1, 1, 1)))
    assert people[0].user_id is not None
    driver.send(by=people[0].user_id)
    driver.act(people[1].id)

    evaluation = driver.evaluate()

    view = evaluation.participant(people[2].id)
    assert view.next_action is NextAction.approve_and_sign
    assert view.needs_plate
