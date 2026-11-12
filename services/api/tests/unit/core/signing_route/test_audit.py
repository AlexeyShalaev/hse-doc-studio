"""Журнал аудита маршрута: запись по событию истории и пометка подписей маршрута (signing-route.md, 6.7)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from hse_doc_studio.core.identity.redaction import REDACTED, redact
from hse_doc_studio.core.signing_route.audit import (
    EVENT_ACTIONS,
    UNAUDITED_EVENTS,
    RouteAuditAction,
    audit_of_event,
    current_signing_route,
    record_of,
    signing_route_scope,
)
from hse_doc_studio.core.signing_route.entities import EventKind, RouteEvent, RouteStatus, SigningRoute, StopReason

from tests.unit.core.signing_route.world import DOC, T0, make_route, participant


def _route() -> SigningRoute:
    author = participant(1, "author", ["author"])
    route = make_route([author, participant(4, "supervisor", ["supervisor"]), participant(7, "academic", ["acad"])])
    return replace(route, status=RouteStatus.active, round=2, sent_by=author.user_id)


def _event(route: SigningRoute, kind: EventKind, **fields: object) -> RouteEvent:
    return RouteEvent(route.id, route.round, T0, kind, **fields)  # type: ignore[arg-type]


def test__event_actions__every_event_kind_is_audited_or_skipped_on_purpose() -> None:
    assert set(EVENT_ACTIONS) | UNAUDITED_EVENTS == set(EventKind)
    assert not set(EVENT_ACTIONS) & UNAUDITED_EVENTS


@pytest.mark.parametrize("kind", sorted(UNAUDITED_EVENTS))
def test__audit_of_event__freeze_and_resume__no_route_record(kind: EventKind) -> None:
    route = _route()

    assert audit_of_event(route, _event(route, kind, details={"docs": [DOC]})) is None


def test__audit_of_event__sent__composition_of_the_route_and_who_sent() -> None:
    route = replace(_route(), deadline=T0 + timedelta(days=3))
    sender = route.participants[0].user_id

    record = audit_of_event(route, _event(route, EventKind.sent, actor_id=sender))

    assert record is not None
    assert (record.action, record.actor_id) == (RouteAuditAction.send, sender)
    assert record.details == {
        "route_id": str(route.id),
        "profile_id": "topic-approval",
        "round": 2,
        "docs": [DOC],
        "steps": 3,
        "participants": 3,
        "deadline": (T0 + timedelta(days=3)).isoformat(),
        "resend": True,
        "new_version": False,
        "changed_docs": [],
        "versions": [],
    }


def test__audit_of_event__sent_new_version__changed_docs_and_versions() -> None:
    """12.10: `signing_route.send` новой версии называет изменившиеся документы и снятые версии (sha256, размер)."""
    route = _route()
    versions = [{"doc_id": DOC, "sha256": "a" * 64, "size": 1024}]
    details = {"new_version": True, "changed": [DOC], "kept": [], "versions": versions, "comment": "x"}

    record = audit_of_event(
        route, _event(route, EventKind.sent, actor_id=route.participants[0].user_id, details=details)
    )

    assert record is not None
    assert (record.details["new_version"], record.details["changed_docs"]) == (True, [DOC])
    assert record.details["versions"] == versions
    assert "comment" not in record.details


def test__audit_of_event__cancelled__unpinned_documents() -> None:
    route = _route()

    record = audit_of_event(
        route, _event(route, EventKind.cancelled, actor_id=route.participants[0].user_id, details={"unpinned": [DOC]})
    )

    assert record is not None
    assert record.details["unpinned"] == [DOC]


def test__audit_of_event__approved__participant_step_by_position_and_own_slots() -> None:
    route = _route()
    supervisor = route.participants[1]

    record = audit_of_event(
        route, _event(route, EventKind.approved, actor_id=supervisor.user_id, participant_id=supervisor.id)
    )

    assert record is not None
    assert record.action is RouteAuditAction.approve
    assert record.details == {
        "route_id": str(route.id),
        "profile_id": "topic-approval",
        "round": 2,
        "participant_id": str(supervisor.id),
        "persona": "supervisor",
        "step": 2,
        "user_id": supervisor.user_id.hex,  # type: ignore[union-attr]
        "slots": [{"doc_id": DOC, "slot_id": "supervisor"}],
    }


def test__audit_of_event__signed__document_and_slot() -> None:
    route = _route()
    supervisor = route.participants[1]
    event = _event(
        route,
        EventKind.signed,
        actor_id=supervisor.user_id,
        participant_id=supervisor.id,
        details={"doc_id": DOC, "slot_id": "supervisor"},
    )

    record = audit_of_event(route, event)

    assert record is not None
    assert record.action is RouteAuditAction.sign
    assert (record.details["doc_id"], record.details["slot_id"], record.details["step"]) == (DOC, "supervisor", 2)


def test__audit_of_event__returned__reason_without_the_comment_text() -> None:
    route = _route()
    academic = route.participants[2]
    event = _event(
        route,
        EventKind.returned,
        actor_id=academic.user_id,
        participant_id=academic.id,
        details={"comment": "Уточните цель проекта", "reason": StopReason.returned.value},
    )

    record = audit_of_event(route, event)

    assert record is not None
    assert record.action is RouteAuditAction.return_
    assert record.details["reason"] == "returned"
    assert "comment" not in record.details
    assert "Уточните" not in str(record.details)


def test__audit_of_event__paused_by_the_server__reason_and_no_actor() -> None:
    route = _route()

    record = audit_of_event(route, _event(route, EventKind.paused, details={"reason": StopReason.rebuilt.value}))

    assert record is not None
    assert (record.action, record.actor_id) == (RouteAuditAction.pause, None)
    assert record.details == {
        "route_id": str(route.id),
        "profile_id": "topic-approval",
        "round": 2,
        "reason": "rebuilt",
    }


def test__audit_of_event__paused_because_a_participant_left__names_the_participant() -> None:
    route = _route()
    gone = route.participants[1]
    route = replace(route, status=RouteStatus.paused, stop_reason=StopReason.participant_left, stopped_by=gone.id)
    event = _event(route, EventKind.paused, details={"reason": StopReason.participant_left.value})

    record = audit_of_event(route, event)

    assert record is not None
    assert (record.details["participant_id"], record.details["persona"]) == (str(gone.id), "supervisor")


def test__audit_of_event__reminder_and_repeated_invitation__who_how_and_why() -> None:
    route = _route()
    author, supervisor, academic = route.participants
    invited = replace(academic, user_id=None, invitation_id="inv_1")
    route = replace(route, participants=(author, supervisor, invited))
    reminded = _event(
        route,
        EventKind.reminded,
        actor_id=author.user_id,
        participant_id=supervisor.id,
        details={"trigger": "manual", "delivery": "email"},
    )
    reinvited = _event(
        route,
        EventKind.invited,
        actor_id=author.user_id,
        participant_id=invited.id,
        details={"invitation_id": "inv_1", "trigger": "manual"},
    )

    remind, invite = audit_of_event(route, reminded), audit_of_event(route, reinvited)

    assert remind is not None
    assert invite is not None
    assert (remind.action, remind.details["trigger"], remind.details["delivery"]) == (
        RouteAuditAction.remind,
        "manual",
        "email",
    )
    assert (invite.action, invite.details["invitation_id"]) == (RouteAuditAction.invite, "inv_1")
    assert "user_id" not in invite.details


def test__audit_of_event__automatic_reminder_and_completion__no_actor() -> None:
    route = _route()
    supervisor = route.participants[1]

    remind = audit_of_event(
        route, _event(route, EventKind.reminded, participant_id=supervisor.id, details={"trigger": "waiting"})
    )
    complete = audit_of_event(route, _event(route, EventKind.completed))

    assert remind is not None
    assert complete is not None
    assert (remind.actor_id, remind.details["trigger"]) == (None, "waiting")
    assert (complete.action, complete.details["docs"]) == (RouteAuditAction.complete, [DOC])


def test__record_of__signer_change__participant_and_metadata() -> None:
    route = _route()
    supervisor = route.participants[1]

    record = record_of(
        RouteAuditAction.signer_plate,
        route,
        actor_id=supervisor.user_id,
        participant=supervisor,
        details={"slot_ids": ["supervisor"], "source": "file", "plate_kind": "x509", "cert_id": "1A2B"},
    )

    assert record.action.value == "signing_route.signer_plate"
    assert record.details["step"] == 2
    assert record.details["cert_id"] == "1A2B"


def test__details__survive_the_audit_redaction() -> None:
    """Журнал вычёркивает поля с `key`, `token`, `secret` в имени: в записях маршрута таких имён нет."""
    route = _route()
    supervisor = route.participants[1]
    records = [
        audit_of_event(route, _event(route, kind, actor_id=supervisor.user_id, participant_id=supervisor.id))
        for kind in EVENT_ACTIONS
    ]
    records.append(
        record_of(
            RouteAuditAction.signer_image,
            route,
            actor_id=supervisor.user_id,
            participant=supervisor,
            details={"slot_ids": ["supervisor"], "sha256": "ab", "size": 10, "remember": False},
        )
    )

    for record in records:
        assert record is not None
        assert REDACTED not in str(redact(dict(record.details)))


def test__signing_route_scope__marks_the_block_and_restores_the_outer_value() -> None:
    outer, inner = uuid4(), uuid4()

    assert current_signing_route() is None
    with signing_route_scope(outer):
        with signing_route_scope(inner):
            assert current_signing_route() == inner
        with signing_route_scope(None):
            assert current_signing_route() == outer
        assert current_signing_route() == outer
    assert current_signing_route() is None


def test__signing_route_scope__restored_after_an_error() -> None:
    def fail() -> None:
        with signing_route_scope(uuid4()):
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        fail()

    assert current_signing_route() is None


def test__audit_of_event__skipped__participant_pairs_kept_marks_and_refrozen() -> None:
    route = _route()
    author, _, academic = route.participants
    pairs = [{"doc_id": DOC, "slot_id": "acad"}]

    record = audit_of_event(
        route,
        _event(
            route,
            EventKind.skipped,
            actor_id=author.user_id,
            participant_id=academic.id,
            details={"slots": pairs, "kept_marks": [DOC], "refrozen": []},
        ),
    )

    assert record is not None
    assert (record.action, record.actor_id) == (RouteAuditAction.skip, author.user_id)
    assert record.details["participant_id"] == str(academic.id)
    assert (record.details["slots"], record.details["kept_marks"], record.details["refrozen"]) == (pairs, [DOC], [])
