"""Расчёт маршрута: очередь, состояния участников, придержанные картинки, уведомления (разделы 4 и 5)."""

from __future__ import annotations

from dataclasses import replace

from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.effects import Notify, Withhold
from hse_doc_studio.core.signing_route.engine import notice_for
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    NextAction,
    Notice,
    ParticipantState,
    RequestOutcome,
    RoutePhase,
    RouteStatus,
)
from hse_doc_studio.core.signing_route.transitions import cancel, mark_notified, return_route, send

from tests.unit.core.signing_route.world import (
    DOC,
    T0,
    Driver,
    World,
    by_persona,
    make_route,
    participant,
    signer,
)

_PERSONAS = ("author", "supervisor", "academic_supervisor")


def _images(*, parallel: bool = False) -> Driver:
    """Все картинкой: автор, научрук, академрук; при `parallel` руководители одним шагом."""
    world = World(modes=dict.fromkeys(_PERSONAS, SignMode.image))
    steps = (1, 2, 2) if parallel else (1, 2, 3)
    people = [participant(step, persona, [persona]) for step, persona in zip(steps, _PERSONAS, strict=True)]
    return Driver(world, make_route(people))


def _send_by_author(driver: Driver) -> None:
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None
    driver.send(by=author.user_id)


def test__evaluate__draft__everyone_waits_and_nothing_happens() -> None:
    driver = _images()

    evaluation = driver.evaluate()

    assert evaluation.status is RouteStatus.draft
    assert evaluation.phase is None
    assert evaluation.effects == ()
    assert {v.state for v in evaluation.participants} == {ParticipantState.waiting}


def test__evaluate__just_sent__withholds_images_of_those_who_have_not_approved() -> None:
    driver = _images()
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None
    driver.route = send(driver.route, driver.world.facts(), by=author.user_id, at=T0)

    evaluation = driver.evaluate()

    withheld = {e for e in evaluation.effects if isinstance(e, Withhold)}
    assert withheld == {Withhold(DOC, "supervisor"), Withhold(DOC, "academic_supervisor")}


def test__evaluate__just_sent__requests_approval_from_the_next_step_only() -> None:
    driver = _images()
    people = by_persona(driver.route)
    assert people["author"].user_id is not None
    driver.route = send(driver.route, driver.world.facts(), by=people["author"].user_id, at=T0)

    evaluation = driver.evaluate()

    notices = [e for e in evaluation.effects if isinstance(e, Notify)]
    assert notices == [Notify(Notice.request, (people["supervisor"].id,), outcome=RequestOutcome.approve)]


def test__evaluate__sent__steps_progress_one_by_one() -> None:
    driver = _images()
    _send_by_author(driver)

    evaluation = driver.evaluate()

    people = by_persona(driver.route)
    assert (evaluation.phase, evaluation.current_step, evaluation.step_position) == (RoutePhase.approval, 2, 2)
    assert evaluation.participant(people["author"].id).state is ParticipantState.done
    assert evaluation.participant(people["supervisor"].id).state is ParticipantState.to_approve
    assert evaluation.participant(people["academic_supervisor"].id).state is ParticipantState.waiting


def test__evaluate__approved__releases_his_image() -> None:
    driver = _images()
    _send_by_author(driver)
    supervisor = by_persona(driver.route)["supervisor"]
    driver.act(supervisor.id)

    assert driver.world.image_visible(supervisor.assignments[0])
    assert not driver.world.image_visible(by_persona(driver.route)["academic_supervisor"].assignments[0])


def test__evaluate__parallel_step__next_step_waits_for_everyone_in_it() -> None:
    world = World(modes=dict.fromkeys((*_PERSONAS, "co_supervisor"), SignMode.image))
    people = [
        participant(1, "author", ["author"]),
        participant(2, "supervisor", ["supervisor"]),
        participant(2, "co_supervisor", ["co_supervisor"]),
        participant(3, "academic_supervisor", ["academic_supervisor"]),
    ]
    driver = Driver(world, make_route(people))
    _send_by_author(driver)
    driver.act(people[1].id)

    evaluation = driver.evaluate()

    assert evaluation.participant(people[2].id).state is ParticipantState.to_approve
    assert evaluation.participant(people[3].id).state is ParticipantState.waiting


def test__evaluate__approver_without_slots__one_approval_in_turn() -> None:
    world = World(modes={"author": SignMode.image})
    people = [participant(1, "author", ["author"]), participant(2, "supervisor")]
    driver = Driver(world, make_route(people))
    _send_by_author(driver)

    view = driver.evaluate().participant(people[1].id)

    assert (view.next_action, view.remaining_actions) == (NextAction.approve, 1)
    driver.run()
    assert driver.route.status is RouteStatus.completed


def test__evaluate__invited_participant__step_waits_without_requests() -> None:
    driver = _images()
    people = by_persona(driver.route)
    driver.route = driver.route.with_participant(replace(people["supervisor"], user_id=None))
    _send_by_author(driver)

    evaluation = driver.evaluate()

    assert evaluation.participant(people["supervisor"].id).state is ParticipantState.invited
    assert evaluation.current_step == 2
    assert not any(isinstance(e, Notify) for e in evaluation.effects)


def test__evaluate__invitation_accepted_in_turn__requests_approval() -> None:
    driver = _images()
    people = by_persona(driver.route)
    supervisor = people["supervisor"]
    driver.route = driver.route.with_participant(replace(supervisor, user_id=None))
    _send_by_author(driver)
    driver.route = driver.route.with_participant(
        replace(driver.route.participant(supervisor.id), user_id=supervisor.user_id)
    )

    evaluation = driver.evaluate()

    assert Notify(Notice.request, (supervisor.id,), outcome=RequestOutcome.approve) in evaluation.effects


def test__evaluate__already_requested_this_round__not_requested_again() -> None:
    driver = _images()
    _send_by_author(driver)
    supervisor = by_persona(driver.route)["supervisor"]

    evaluation = driver.evaluate()

    assert driver.route.participant(supervisor.id).notified is not None
    assert evaluation.effects == ()


def test__evaluate__new_round__requests_again() -> None:
    driver = _images()
    _send_by_author(driver)
    author, supervisor = by_persona(driver.route)["author"], by_persona(driver.route)["supervisor"]
    assert author.user_id is not None
    driver.route = send(cancel(driver.route), driver.world.facts(), by=author.user_id, at=T0)

    evaluation = driver.evaluate()

    assert Notify(Notice.request, (supervisor.id,), outcome=RequestOutcome.approve) in evaluation.effects


def test__evaluate__returned__returner_marked_and_nobody_acts() -> None:
    driver = _images()
    _send_by_author(driver)
    supervisor = by_persona(driver.route)["supervisor"]
    driver.route = return_route(driver.route, driver.world.facts(), supervisor.id)

    evaluation = driver.evaluate()

    assert evaluation.participant(supervisor.id).state is ParticipantState.returned
    assert {v.next_action for v in evaluation.participants} <= {NextAction.wait, NextAction.done}
    assert evaluation.effects == ()


def test__evaluate__cancelled_route_doc_rebuilt__leaves_everything_as_is() -> None:
    driver = _images()
    _send_by_author(driver)
    driver.route = cancel(driver.route)
    driver.world.compiled[DOC] = "c" * 64

    evaluation = driver.evaluate()

    assert (evaluation.status, evaluation.stop, evaluation.effects) == (RouteStatus.cancelled, None, ())


def test__evaluate__visible_pades_last_changer__approves_and_signs_at_once() -> None:
    world = World(modes={"author": SignMode.image, "supervisor": SignMode.image_crypto})
    people = [participant(1, "author", ["author"]), participant(2, "supervisor", ["supervisor"])]
    driver = Driver(world, make_route(people))
    _send_by_author(driver)

    action = driver.act(people[1].id)

    assert action is NextAction.approve_and_sign
    assert driver.route.status is RouteStatus.completed
    assert driver.world.resets == 0


def test__evaluate__pades_signer_before_image__signs_final_pdf_after_freeze() -> None:
    world = World(modes={"author": SignMode.crypto_invisible, "supervisor": SignMode.image})
    people = [participant(1, "author", ["author"]), participant(2, "supervisor", ["supervisor"])]
    driver = Driver(world, make_route(people))
    _send_by_author(driver)
    driver.act(people[1].id)

    evaluation = driver.evaluate()

    assert evaluation.phase is RoutePhase.signing
    assert evaluation.participant(people[0].id).next_action is NextAction.sign
    assert Notify(Notice.request, (people[0].id,), outcome=RequestOutcome.sign) in driver.world.notices


def test__evaluate__image_not_uploaded__needs_image() -> None:
    driver = _images()
    driver.world.slots["supervisor"] = replace(driver.world.slots["supervisor"], png_path=None)
    _send_by_author(driver)

    view = driver.evaluate().participant(by_persona(driver.route)["supervisor"].id)

    assert view.needs_image


def test__evaluate__all_approved__completed_with_notice_to_everyone() -> None:
    driver = _images()
    _send_by_author(driver)
    people = by_persona(driver.route)
    driver.act(people["supervisor"].id)
    route = driver.route
    driver.act(people["academic_supervisor"].id)

    assert driver.route.status is RouteStatus.completed
    assert driver.route.completed_at is not None
    assert driver.world.notices[-1] == notice_for(route, Notice.completed)


def test__notice_for__cancelled__only_those_who_got_a_request() -> None:
    driver = _images()
    _send_by_author(driver)
    supervisor = by_persona(driver.route)["supervisor"]

    notice = notice_for(driver.route, Notice.cancelled)

    assert notice == Notify(Notice.cancelled, (supervisor.id,))


def test__notice_for__returned__sender_and_who_approved() -> None:
    driver = _images()
    _send_by_author(driver)
    people = by_persona(driver.route)
    driver.act(people["supervisor"].id)

    notice = notice_for(driver.route, Notice.returned)

    assert notice == Notify(Notice.returned, (people["author"].id, people["supervisor"].id), sender=True)


def test__mark_notified__same_turn_other_outcome__not_requested_again() -> None:
    driver = _images()
    _send_by_author(driver)
    supervisor = by_persona(driver.route)["supervisor"]
    driver.route = mark_notified(driver.route, supervisor.id, RequestOutcome.approve_sign, at=T0)

    evaluation = driver.evaluate()

    assert evaluation.effects == ()


def test__engine__manual_freeze_before_route__route_freezes_the_version_sent_and_drops_old_signatures() -> None:
    # Автор зафиксировал и подписал документ вручную, потом пересобрал и отправил на подпись: фиксация старой сборки
    # к версии на подписи не относится (signing-route.md, 12.8.1). Пока маршрут в согласовании, она лежит как есть,
    # а фиксация маршрута после согласий заменяет её фиксацией версии на подписи и снимает подписи над старой.
    world = World(modes={"author": SignMode.detached_text, "supervisor": SignMode.image})
    world.freeze(DOC)
    world.sign(DocSlot(DOC, "author"))
    manual = world.frozen[DOC]
    world.compiled[DOC] = "c" * 64
    people = [participant(1, "author", ["author"]), participant(2, "supervisor", ["supervisor"])]
    for p in people:
        assert p.user_id is not None
        world.plates[p.user_id] = signer(p.persona)
    driver = Driver(world, make_route(people))

    author = by_persona(driver.route)["author"].user_id
    assert author is not None
    driver.send(by=author)

    assert driver.route.phase is RoutePhase.approval
    assert world.frozen[DOC] == manual
    assert world.pinned[DOC] == "c" * 64

    driver.run()

    assert driver.route.status is RouteStatus.completed
    frozen = world.frozen[DOC]
    assert frozen.source_sha256 == world.pinned[DOC]
    assert frozen.sha256 != manual.sha256
    assert world.resets == 1
    assert world.detached[DOC]["author"].pdf_sha256 == frozen.sha256
