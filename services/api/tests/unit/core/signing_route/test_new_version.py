"""Раздел 12.6: «Отправить новую версию» и согласия по документам.

Маршрут на два документа: автор (картинка) на обоих, научрук (ЭП) на изменяемом `DOC`, рецензент (ЭП) на
неизменном `DOC2`, академрук (картинка) на обоих. Все ключи известны. Инварианты раздела 2 проверяет `Driver`
на каждом шаге: согласия по порядку, картинка на документе только после согласия его версии.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signatures.plan import DocFacts
from hse_doc_studio.core.signing_route.effects import Freeze, Notify, Release, Withhold
from hse_doc_studio.core.signing_route.engine import RouteFacts, approved_docs, evaluate
from hse_doc_studio.core.signing_route.entities import (
    DocSnapshot,
    NextAction,
    Notice,
    ParticipantState,
    RequestOutcome,
    RouteConflictError,
    RoutePhase,
    RouteStatus,
    StopReason,
)
from hse_doc_studio.core.signing_route.transitions import cancel, return_route, send
from hse_doc_studio.core.signing_route.versions import (
    DocChange,
    keeps_approval,
    losing_approval,
    lost_docs,
    version_changes,
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

_NEW = "c" * 64


def _completed() -> Driver:
    world = World(
        modes={
            "author": SignMode.image,
            "supervisor": SignMode.detached_text,
            "reviewer": SignMode.detached_text,
            "academic_supervisor": SignMode.image,
        },
        docs=(DOC, DOC2),
    )
    people = [
        participant(1, "author", ["author"], docs=(DOC, DOC2)),
        participant(2, "supervisor", ["supervisor"], docs=(DOC,)),
        participant(3, "reviewer", ["reviewer"], docs=(DOC2,)),
        participant(4, "academic_supervisor", ["academic_supervisor"], docs=(DOC, DOC2)),
    ]
    for p in people:
        assert p.user_id is not None
        world.plates[p.user_id] = signer(p.persona)
    driver = Driver(world, make_route(people, docs=(DOC, DOC2)))
    driver.send(by=_id(driver, "author"))
    driver.run()
    assert driver.route.status is RouteStatus.completed
    driver.actions.clear()
    return driver


def _id(driver: Driver, persona: str) -> UUID:
    user_id = by_persona(driver.route)[persona].user_id
    assert user_id is not None
    return user_id


def _pid(driver: Driver, persona: str) -> UUID:
    return by_persona(driver.route)[persona].id


# --- кандидат --------------------------------------------------------------------------------------------------------


def test__candidate__source_replaced_by_working_build_unbuilt_keeps_pinned() -> None:
    facts = RouteFacts(
        docs={
            "rebuilt": DocFacts("a" * 64, "m", working_sha256="b" * 64),
            "unbuilt": DocFacts("a" * 64, "m", working_sha256=None),
            "nothing": DocFacts(None, "m", working_sha256=None),
        },
        state=World(modes={}).state(),
    )

    candidate = facts.candidate()

    assert {doc_id: doc.compiled_sha256 for doc_id, doc in candidate.docs.items()} == {
        "rebuilt": "b" * 64,
        "unbuilt": "a" * 64,
        "nothing": None,
    }
    assert candidate.doc("rebuilt").marks_digest == "m"
    assert (candidate.state, candidate.withheld) == (facts.state, facts.withheld)


def test__version_changes__same_changed_and_new_against_the_pinned_version() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW
    route = replace(driver.route, docs=(*driver.route.docs, "appendix"))

    changes = version_changes(route, driver.world.facts().candidate())

    assert changes.docs == {DOC: DocChange.changed, DOC2: DocChange.same, "appendix": DocChange.new}
    assert (changes.changed, changes.kept, changes.new, changes.to_pin) == (
        (DOC,),
        (DOC2,),
        ("appendix",),
        (DOC, "appendix"),
    )
    assert changes.new_version


def test__version_changes__first_send__every_document_new_and_not_a_new_version() -> None:
    world = World(modes={"author": SignMode.image}, docs=(DOC, DOC2))
    route = make_route([participant(1, "author", ["author"], docs=(DOC, DOC2))], docs=(DOC, DOC2))

    changes = version_changes(route, world.facts().candidate())

    assert (changes.new, changes.any, changes.new_version) == ((DOC, DOC2), True, False)


# --- откуда отправлять ------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rebuilt", [False, True], ids=["без пересборки", "пересборка дала те же байты"])
@pytest.mark.parametrize("status", [RouteStatus.active, RouteStatus.completed])
def test__send__running_or_completed_route_without_changes__nothing_changed(rebuilt: bool, status: RouteStatus) -> None:
    driver = _completed()
    if rebuilt:
        driver.world.compiled[DOC] = driver.world.pinned[DOC]
    route = replace(driver.route, status=status)

    with pytest.raises(RouteConflictError) as error:
        send(route, driver.world.facts().candidate(), by=_id(driver, "author"), at=T0)

    assert error.value.code == "nothing_changed"


@pytest.mark.parametrize("status", [RouteStatus.active, RouteStatus.completed])
def test__send__running_or_completed_route_with_changes__active_next_round(status: RouteStatus) -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW
    route = replace(driver.route, status=status)

    sent = send(route, driver.world.facts().candidate(), by=_id(driver, "author"), at=T0 + timedelta(days=1))

    assert (sent.status, sent.phase, sent.round, sent.stop_reason) == (
        RouteStatus.active,
        RoutePhase.approval,
        route.round + 1,
        None,
    )
    assert (sent.participants, sent.steps) == (
        tuple(replace(p, approval=sent.participant(p.id).approval, notified=None) for p in route.participants),
        route.steps,
    )


def test__send__stopped_route_without_changes__sent_again() -> None:
    driver = _completed()
    route = replace(driver.route, status=RouteStatus.paused, phase=None, stop_reason=StopReason.participant_left)

    sent = send(route, driver.world.facts().candidate(), by=_id(driver, "author"), at=T0)

    assert (sent.status, sent.round) == (RouteStatus.active, route.round + 1)


# --- снимок и время версии --------------------------------------------------------------------------------------------


def test__send__new_version__changed_document_gets_new_sent_at_kept_one_keeps_its_own() -> None:
    driver = _completed()
    first = driver.route.snapshot
    driver.world.compiled[DOC] = _NEW
    later = T0 + timedelta(days=1)

    sent = send(driver.route, driver.world.facts().candidate(), by=_id(driver, "author"), at=later)

    assert sent.snapshot[DOC].compiled_sha256 == _NEW
    assert (sent.snapshot[DOC].sent_at, sent.doc_sent_at(DOC)) == (later, later)
    assert sent.snapshot[DOC2] == first[DOC2]
    assert sent.doc_sent_at(DOC2) == first[DOC2].sent_at == driver.route.sent_at
    assert sent.sent_at == later


def test__send__route_from_0_20_0_without_sent_at__kept_document_keeps_the_route_send_time() -> None:
    driver = _completed()
    legacy = replace(
        driver.route, snapshot={doc_id: replace(seen, sent_at=None) for doc_id, seen in driver.route.snapshot.items()}
    )
    assert legacy.doc_sent_at(DOC2) == legacy.sent_at
    driver.world.compiled[DOC] = _NEW

    sent = send(legacy, driver.world.facts().candidate(), by=_id(driver, "author"), at=T0 + timedelta(days=1))

    assert sent.snapshot[DOC2].sent_at == legacy.sent_at


def test__doc_snapshot__sent_at_is_not_a_fingerprint() -> None:
    assert DocSnapshot("a", "m", sent_at=T0) == DocSnapshot("a", "m")


# --- согласия по документам -------------------------------------------------------------------------------------------


def test__send__new_version__approvals_carried_and_counted_per_document() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW
    candidate = driver.world.facts().candidate()

    sent = send(driver.route, candidate, by=_id(driver, "author"), at=T0)

    approved = {p.persona: approved_docs(sent, p, candidate) for p in sent.participants}
    assert approved == {
        "author": {DOC, DOC2},  # отправка это его согласие
        "supervisor": frozenset(),
        "reviewer": {DOC2},
        "academic_supervisor": {DOC2},
    }
    assert all(p.approval is not None and p.approval.round == sent.round for p in sent.participants)


def test__preview__keeps_approval_and_who_loses_it() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW
    candidate = driver.world.facts().candidate()
    route = driver.route

    keeps = {p.persona: keeps_approval(route, candidate, p) for p in route.participants}
    lost = {p.persona: lost_docs(route, candidate, p) for p in route.participants}

    assert keeps == {"author": False, "supervisor": False, "reviewer": True, "academic_supervisor": False}
    assert lost == {"author": (DOC,), "supervisor": (DOC,), "reviewer": (), "academic_supervisor": (DOC,)}
    assert losing_approval(route, candidate) == tuple(
        _pid(driver, p) for p in ("author", "supervisor", "academic_supervisor")
    )


def test__new_version__images_stay_on_unchanged_document_withheld_on_changed_one() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW

    evaluation = driver.send(by=_id(driver, "author"))

    academic = _pid(driver, "academic_supervisor")
    files = [e for e in evaluation.effects if isinstance(e, Withhold | Release | Freeze)]
    assert files == [Withhold(DOC, "academic_supervisor")]
    assert driver.world.image_visible(driver.route.participant(academic).assignments[1])  # на DOC2
    assert driver.world.image_visible(driver.route.participant(_pid(driver, "author")).assignments[0])


def test__new_version__reapproval_starts_from_step_one_in_order_unchanged_participant_holds_nothing() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW

    evaluation = driver.send(by=_id(driver, "author"))

    states = {p.persona: evaluation.participant(p.id).state for p in driver.route.participants}
    assert states == {
        "author": ParticipantState.done,
        "supervisor": ParticipantState.to_approve,
        "reviewer": ParticipantState.done,
        "academic_supervisor": ParticipantState.waiting,
    }
    assert evaluation.current_step == 2
    shown = {
        p.persona: (evaluation.participant(p.id).approved, evaluation.participant(p.id).approved_docs)
        for p in driver.route.participants
    }
    assert shown == {
        "author": (True, {DOC, DOC2}),
        "supervisor": (False, frozenset()),
        "reviewer": (True, {DOC2}),
        "academic_supervisor": (False, {DOC2}),
    }
    requests = [e for e in evaluation.effects if isinstance(e, Notify)]
    assert requests == [Notify(Notice.request, (_pid(driver, "supervisor"),), outcome=RequestOutcome.approve)]


def test__new_version__run_to_completion__only_changed_document_refrozen_kept_signatures_untouched() -> None:
    driver = _completed()
    kept_frozen = driver.world.frozen[DOC2]
    kept_signatures = dict(driver.world.detached[DOC2])
    old_frozen = driver.world.frozen[DOC]
    driver.world.compiled[DOC] = _NEW

    driver.send(by=_id(driver, "author"))
    driver.run()

    assert driver.route.status is RouteStatus.completed
    assert (driver.world.frozen[DOC2], driver.world.detached[DOC2]) == (kept_frozen, kept_signatures)
    assert driver.world.frozen[DOC] != old_frozen
    assert driver.world.frozen[DOC].source_sha256 == _NEW
    assert driver.world.resets == 1  # подпись научрука над прежним B изменившегося документа
    assert driver.actions[_pid(driver, "reviewer")] == 0
    # Научрук ЭП до картинки академрука: согласовать, затем подписать новый B (таблица 4.4).
    assert (driver.actions[_pid(driver, "supervisor")], driver.actions[_pid(driver, "academic_supervisor")]) == (2, 1)


def test__new_version__unchanged_participant_lost_signature__signs_again_without_holding_steps() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW
    driver.world.unsign(driver.route.participant(_pid(driver, "reviewer")).assignments[0])

    evaluation = driver.send(by=_id(driver, "author"))

    reviewer = evaluation.participant(_pid(driver, "reviewer"))
    assert (reviewer.state, reviewer.next_action) == (ParticipantState.waiting, NextAction.wait)
    assert evaluation.current_step == 2


def test__new_version__parallel_authors_of_personal_documents__only_the_changed_one_approves_again() -> None:
    world = World(modes={"a": SignMode.image, "b": SignMode.image, "supervisor": SignMode.image}, docs=(DOC, DOC2))
    people = [
        participant(1, "a", ["a"], docs=(DOC,)),
        participant(1, "b", ["b"], docs=(DOC2,)),
        participant(2, "supervisor", ["supervisor"], docs=(DOC, DOC2)),
    ]
    driver = Driver(world, make_route(people, docs=(DOC, DOC2)))
    driver.send(by=_id(driver, "supervisor"))
    driver.run()
    assert driver.route.status is RouteStatus.completed
    world.compiled[DOC] = _NEW

    evaluation = driver.send(by=_id(driver, "supervisor"))

    states = {p.persona: evaluation.participant(p.id).state for p in driver.route.participants}
    assert states == {
        "a": ParticipantState.to_approve,
        "b": ParticipantState.done,
        "supervisor": ParticipantState.waiting,
    }


def test__send__again_after_return__approvals_carried_return_comment_cleared() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW
    driver.send(by=_id(driver, "author"))
    driver.route = return_route(driver.route, driver.world.facts(), _pid(driver, "supervisor"))

    sent = send(driver.route, driver.world.facts().candidate(), by=_id(driver, "author"), at=T0)

    assert (sent.status, sent.stop_reason, sent.stopped_by) == (RouteStatus.active, None, None)
    assert approved_docs(sent, sent.participant(_pid(driver, "reviewer")), driver.world.facts()) == {DOC2}


def test__send__after_cancel_with_changes__kept_document_and_its_approvals_stay() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW
    driver.send(by=_id(driver, "author"))
    driver.route = cancel(driver.route)
    driver.world.compiled[DOC] = "e" * 64
    candidate = driver.world.facts().candidate()

    sent = send(driver.route, candidate, by=_id(driver, "author"), at=T0)

    # Отмена сняла версии на подписи (12.4): прежней версии нет, документы отправляются заново, а согласия
    # переносятся по отпечаткам, как всегда.
    assert driver.route.snapshot == {}
    assert version_changes(driver.route, candidate).docs == {DOC: DocChange.new, DOC2: DocChange.new}
    assert evaluate(sent, candidate).stop is None
    assert approved_docs(sent, sent.participant(_pid(driver, "reviewer")), candidate) == {DOC2}


def test__send__new_version__round_changed_docs_names_only_replaced_documents() -> None:
    """Раунд новой версии знает, какие документы он сменил (`DocSnapshot.replaced` и время отправки), R16."""
    driver = _completed()
    assert driver.route.round_changed_docs == ()
    driver.world.compiled[DOC] = _NEW

    sent = send(driver.route, driver.world.facts().candidate(), by=_id(driver, "author"), at=T0 + timedelta(hours=1))

    assert sent.round_changed_docs == (DOC,)
    assert (sent.snapshot[DOC].replaced, sent.snapshot[DOC2].replaced) == (True, False)
    assert sent.snapshot[DOC2].sent_at == driver.route.doc_sent_at(DOC2)


def test__cancel__forgets_the_sent_versions() -> None:
    driver = _completed()
    driver.world.compiled[DOC] = _NEW
    driver.send(by=_id(driver, "author"))

    cancelled = cancel(driver.route)

    assert (cancelled.snapshot, cancelled.round_changed_docs) == ({}, ())
