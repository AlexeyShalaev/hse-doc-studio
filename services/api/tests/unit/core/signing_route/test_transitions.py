"""Переходы маршрута: отправка и повторная отправка, согласие, возврат, отмена, применение расчёта (5.3, 5.4, 5.6)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signing_route.engine import approval_token, approved_docs
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    RouteConflictError,
    RouteInputError,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
)
from hse_doc_studio.core.signing_route.transitions import (
    apply_evaluation,
    approve,
    archive,
    can_transition,
    cancel,
    check_route,
    ensure_transition,
    refresh_snapshot,
    return_route,
    send,
)

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
_S = RouteStatus


def _images(docs: tuple[str, ...] = (DOC,)) -> Driver:
    world = World(modes=dict.fromkeys(_PERSONAS, SignMode.image), docs=docs)
    people = [participant(step, persona, [persona], docs=docs) for step, persona in enumerate(_PERSONAS, start=1)]
    return Driver(world, make_route(people, docs=docs))


def _author_id(route: SigningRoute) -> UUID:
    user_id = by_persona(route)["author"].user_id
    assert user_id is not None
    return user_id


@pytest.mark.parametrize(
    ("source", "target", "allowed"),
    [
        (_S.draft, _S.active, True),
        (_S.active, _S.active, True),
        (_S.active, _S.returned, True),
        (_S.paused, _S.active, True),
        (_S.completed, _S.paused, True),
        (_S.completed, _S.active, True),
        (_S.cancelled, _S.archived, True),
        (_S.paused, _S.cancelled, True),
        (_S.draft, _S.completed, False),
        (_S.returned, _S.completed, False),
        (_S.archived, _S.active, False),
        (_S.active, _S.archived, False),
    ],
)
def test__can_transition__follows_state_diagram(source: RouteStatus, target: RouteStatus, allowed: bool) -> None:
    assert can_transition(source, target) is allowed


def test__ensure_transition__not_allowed__conflict() -> None:
    with pytest.raises(RouteConflictError) as error:
        ensure_transition(_S.archived, _S.active)

    assert error.value.code == "invalid_transition"


def test__send__draft__new_round_with_snapshot() -> None:
    driver = _images()

    route = send(driver.route, driver.world.facts(), by=uuid4(), at=T0)

    assert (route.status, route.phase, route.round, route.sent_at) == (_S.active, RoutePhase.approval, 1, T0)
    assert route.snapshot == driver.world.facts().snapshot((DOC,))


def test__send__sender_in_first_step__sending_is_his_approval() -> None:
    driver = _images()
    author = by_persona(driver.route)["author"]
    assert author.user_id is not None

    route = send(driver.route, driver.world.facts(), by=author.user_id, at=T0)

    approval = route.participant(author.id).approval
    assert approval is not None
    assert (approval.round, dict(approval.tokens)) == (1, {DOC: approval_token(driver.world.facts().doc(DOC))})


def test__send__sender_in_later_step__approves_in_turn_like_everyone() -> None:
    driver = _images()
    supervisor = by_persona(driver.route)["supervisor"]
    assert supervisor.user_id is not None

    route = send(driver.route, driver.world.facts(), by=supervisor.user_id, at=T0)

    assert route.participant(supervisor.id).approval is None


def test__send__active_route_nothing_changed__nothing_changed() -> None:
    driver = _images()
    route = send(driver.route, driver.world.facts(), by=uuid4(), at=T0)

    with pytest.raises(RouteConflictError) as error:
        send(route, driver.world.facts().candidate(), by=uuid4(), at=T0)

    assert error.value.code == "nothing_changed"


def test__send__archived_route__invalid_transition() -> None:
    driver = _images()
    route = archive(cancel(send(driver.route, driver.world.facts(), by=uuid4(), at=T0)))

    with pytest.raises(RouteConflictError) as error:
        send(route, driver.world.facts(), by=uuid4(), at=T0)

    assert error.value.code == "invalid_transition"


def test__send__again_after_return_doc_unchanged__approval_carried_over() -> None:
    driver = _images()
    driver.send(by=_author_id(driver.route))
    people = by_persona(driver.route)
    driver.act(people["supervisor"].id)
    driver.route = return_route(driver.route, driver.world.facts(), people["academic_supervisor"].id)

    route = send(driver.route, driver.world.facts(), by=uuid4(), at=T0)

    approval = route.participant(people["supervisor"].id).approval
    assert approval is not None
    assert (approval.round, approval.phase) == (2, RoutePhase.approval)


def test__send__again_after_rebuild__approval_carried_with_old_tokens_and_no_longer_valid() -> None:
    driver = _images()
    driver.send(by=_author_id(driver.route))
    supervisor = by_persona(driver.route)["supervisor"]
    driver.act(supervisor.id)
    old = driver.route.participant(supervisor.id).approval
    driver.world.compiled[DOC] = "c" * 64
    driver.settle()
    candidate = driver.world.facts().candidate()

    route = send(driver.route, candidate, by=uuid4(), at=T0)

    approval = route.participant(supervisor.id).approval
    assert approval is not None
    assert old is not None
    assert (approval.round, dict(approval.tokens)) == (2, dict(old.tokens))
    assert approved_docs(route, route.participant(supervisor.id), candidate) == frozenset()


def test__send__again_one_of_two_docs_rebuilt__only_its_signers_lose_approval() -> None:
    world = World(modes=dict.fromkeys(_PERSONAS, SignMode.image), docs=(DOC, DOC2))
    people = [
        participant(1, "author", ["author"], docs=(DOC, DOC2)),
        participant(2, "supervisor", ["supervisor"], docs=(DOC,)),
        participant(2, "co_supervisor", [], docs=()),
        participant(3, "academic_supervisor", ["academic_supervisor"], docs=(DOC2,)),
    ]
    driver = Driver(world, make_route(people, docs=(DOC, DOC2)))
    driver.send(by=_author_id(driver.route))
    for p in people[1:]:
        driver.act(p.id)
    world.compiled[DOC] = "c" * 64
    driver.settle()
    candidate = world.facts().candidate()

    route = send(driver.route, candidate, by=uuid4(), at=T0)

    kept = {p.persona for p in route.participants if approved_docs(route, p, candidate) == set(p.doc_ids(route.docs))}
    assert kept == {"academic_supervisor"}
    author = by_persona(route)["author"]
    assert approved_docs(route, author, candidate) == {DOC2}


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda r: replace(r, participants=()), "no_participants"),
        (lambda r: r.with_participant(replace(r.participants[0], step=0)), "bad_step"),
        (lambda r: replace(r, participants=(r.participants[0], r.participants[0])), "duplicate_participant"),
        (
            lambda r: r.with_participant(replace(r.participants[1], assignments=r.participants[0].assignments)),
            "duplicate_slot",
        ),
        (
            lambda r: r.with_participant(replace(r.participants[0], assignments=(DocSlot("other", "author"),))),
            "unknown_doc",
        ),
    ],
    ids=["нет участников", "шаг 0", "участник дважды", "слот у двоих", "чужой документ"],
)
def test__check_route__broken_route__input_error(change: Callable[[SigningRoute], SigningRoute], code: str) -> None:
    route = change(_images().route)

    with pytest.raises(RouteInputError) as error:
        check_route(route)

    assert error.value.code == code


def test__approve__not_in_turn__not_your_turn() -> None:
    driver = _images()
    driver.send(by=_author_id(driver.route))
    academic = by_persona(driver.route)["academic_supervisor"]

    with pytest.raises(RouteConflictError) as error:
        approve(driver.route, driver.world.facts(), academic.id, at=T0)

    assert error.value.code == "not_your_turn"


def test__approve__no_image__image_required() -> None:
    driver = _images()
    driver.world.slots["supervisor"] = replace(driver.world.slots["supervisor"], png_path=None)
    driver.send(by=_author_id(driver.route))

    with pytest.raises(RouteConflictError) as error:
        approve(driver.route, driver.world.facts(), by_persona(driver.route)["supervisor"].id, at=T0)

    assert error.value.code == "image_required"


def test__approve__plate_data_unknown__plate_required() -> None:
    world = World(modes={"author": SignMode.image, "supervisor": SignMode.detached_text})
    people = [participant(1, "author", ["author"]), participant(2, "supervisor", ["supervisor"])]
    driver = Driver(world, make_route(people))
    driver.send(by=_author_id(driver.route))

    with pytest.raises(RouteConflictError) as error:
        approve(driver.route, world.facts(), people[1].id, at=T0)

    assert error.value.code == "plate_required"


def test__approve__stranger__not_participant() -> None:
    driver = _images()
    driver.send(by=_author_id(driver.route))

    with pytest.raises(RouteConflictError) as error:
        approve(driver.route, driver.world.facts(), uuid4(), at=T0)

    assert error.value.code == "not_participant"


def test__approve__after_freeze__remembers_it_was_given_in_signing_phase() -> None:
    world = World(modes={"author": SignMode.image, "supervisor": SignMode.crypto_invisible})
    people = [participant(1, "author", ["author"]), participant(2, "supervisor", ["supervisor"])]
    driver = Driver(world, make_route(people))
    driver.send(by=_author_id(driver.route))

    route = approve(driver.route, world.facts(), people[1].id, at=T0)

    approval = route.participant(people[1].id).approval
    assert approval is not None
    assert approval.phase is RoutePhase.signing


def test__return_route__not_in_turn__not_your_turn() -> None:
    driver = _images()
    driver.send(by=_author_id(driver.route))

    with pytest.raises(RouteConflictError) as error:
        return_route(driver.route, driver.world.facts(), by_persona(driver.route)["academic_supervisor"].id)

    assert error.value.code == "not_your_turn"


def test__return_route__in_turn__returned_by_him() -> None:
    driver = _images()
    driver.send(by=_author_id(driver.route))
    supervisor = by_persona(driver.route)["supervisor"]

    route = return_route(driver.route, driver.world.facts(), supervisor.id)

    assert (route.status, route.stop_reason, route.stopped_by) == (_S.returned, StopReason.returned, supervisor.id)


def test__cancel__paused_route__cancelled() -> None:
    driver = _images()
    driver.send(by=_author_id(driver.route))
    driver.world.compiled[DOC] = "c" * 64
    driver.settle()

    route = cancel(driver.route)

    assert (route.status, route.stop_reason) == (_S.cancelled, None)


@pytest.mark.parametrize("status", [_S.completed, _S.cancelled])
def test__archive__finished_route__archived(status: RouteStatus) -> None:
    route = archive(replace(_images().route, status=status))

    assert route.status is _S.archived


def test__archive__active_route__invalid_transition() -> None:
    with pytest.raises(RouteConflictError):
        archive(replace(_images().route, status=_S.active))


def test__apply_evaluation__completed_route_lost_signature__active_again_without_completed_at() -> None:
    world = World(modes={"author": SignMode.detached_text})
    people = [participant(1, "author", ["author"])]
    assert people[0].user_id is not None
    world.plates[people[0].user_id] = signer("author")
    driver = Driver(world, make_route(people))
    driver.send(by=people[0].user_id)
    driver.run()
    world.unsign(DocSlot(DOC, "author"))

    route = apply_evaluation(driver.route, driver.evaluate(), at=T0)

    assert (route.status, route.phase, route.completed_at) == (_S.active, RoutePhase.signing, None)


def test__refresh_snapshot__keeps_version_that_was_sent_and_when() -> None:
    driver = _images()
    driver.send(by=_author_id(driver.route))
    driver.world.pinned[DOC] = "c" * 64
    driver.world.withheld[DOC].add("author")

    route = refresh_snapshot(driver.route, driver.world.facts())

    snapshot = route.snapshot[DOC]
    assert snapshot.compiled_sha256 == driver.route.snapshot[DOC].compiled_sha256
    assert snapshot.sent_at == driver.route.snapshot[DOC].sent_at is not None
    assert snapshot.marks_digest == driver.world.marks(DOC)
