"""Уведомления маршрута: адресаты, ключ повтора, письма и пометка запросов (docs/design/signing-route.md, 6.6)."""

from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from hse_doc_studio.core.signing_route.effects import Freeze, Notify
from hse_doc_studio.core.signing_route.engine import notice_for
from hse_doc_studio.core.signing_route.entities import (
    Approval,
    Notice,
    Notified,
    RequestOutcome,
    RouteStatus,
    SigningRoute,
)
from hse_doc_studio.core.signing_route.notices import (
    Recipient,
    dedupe_key,
    mails,
    mark_requests,
    notices_in,
    recipients,
)

from tests.unit.core.signing_route.world import T0, make_route, participant


def _route() -> SigningRoute:
    author = participant(1, "author", ["author"])
    route = make_route([author, participant(2, "supervisor", ["supervisor"]), participant(3, "academic", ["acad"])])
    return replace(route, status=RouteStatus.active, round=2, sent_by=author.user_id)


def test__recipients__participant_who_sent_the_route_gets_one_notification_as_sender() -> None:
    route = _route()
    author, supervisor, _ = route.participants

    found = recipients(route, Notify(Notice.completed, (author.id, supervisor.id), sender=True))

    assert found == (
        Recipient(author.user_id, author.id, sender=True),  # type: ignore[arg-type]
        Recipient(supervisor.user_id, supervisor.id),  # type: ignore[arg-type]
    )


def test__recipients__sender_outside_the_route_and_invitee_without_account() -> None:
    route = _route()
    outsider = uuid4()
    invited = replace(route.participants[2], user_id=None, invitation_id="inv_1")
    route = replace(route, sent_by=outsider, participants=(*route.participants[:2], invited))

    found = recipients(route, Notify(Notice.paused, (invited.id,), sender=True))

    assert found == (Recipient(outsider, None, sender=True),)


def test__recipients__whoever_returned_or_cancelled_is_not_notified_of_it() -> None:
    route = _route()
    author, supervisor, academic = route.participants
    approved = Approval(round=route.round, tokens={}, at=T0)
    route = route.with_participant(replace(supervisor, approval=approved))
    route = route.with_participant(replace(academic, approval=approved))

    returned = recipients(route, notice_for(route, Notice.returned), actor_id=academic.user_id)
    cancelled = recipients(route, Notify(Notice.cancelled, (supervisor.id,)), actor_id=supervisor.user_id)
    request = recipients(route, Notify(Notice.request, (supervisor.id,)), actor_id=supervisor.user_id)

    assert [r.user_id for r in returned] == [supervisor.user_id, author.user_id]
    assert cancelled == ()
    assert [r.user_id for r in request] == [supervisor.user_id]


def test__dedupe_key__per_route_round_participant_kind_and_request_turn() -> None:
    route = _route()
    supervisor = route.participants[1]
    who = Recipient(supervisor.user_id, supervisor.id)  # type: ignore[arg-type]
    base = f"signing:{route.id.hex}:2:{supervisor.id.hex}"

    approve = dedupe_key(route, Notify(Notice.request, (supervisor.id,), outcome=RequestOutcome.approve), who)
    combined = dedupe_key(route, Notify(Notice.request, (supervisor.id,), outcome=RequestOutcome.approve_sign), who)
    sign = dedupe_key(route, Notify(Notice.request, (supervisor.id,), outcome=RequestOutcome.sign), who)
    reminder = dedupe_key(route, Notify(Notice.reminder, (supervisor.id,)), who)
    sender = dedupe_key(route, Notify(Notice.paused, sender=True), Recipient(uuid4(), None, sender=True))

    assert approve == combined == f"{base}:signing_request:approve"
    assert sign == f"{base}:signing_request:sign"
    assert reminder == f"{base}:signing_reminder"
    assert sender == f"signing:{route.id.hex}:2:sender:signing_paused"
    assert len(approve) <= 128


def test__mails__request_and_reminder_to_all_returned_and_completed_to_the_author_only() -> None:
    signer, author = Recipient(uuid4(), uuid4()), Recipient(uuid4(), None, sender=True)

    assert mails(Notify(Notice.request), signer) is True
    assert mails(Notify(Notice.reminder), signer) is True
    assert (mails(Notify(Notice.returned), signer), mails(Notify(Notice.returned), author)) == (False, True)
    assert (mails(Notify(Notice.completed), signer), mails(Notify(Notice.completed), author)) == (False, True)
    assert mails(Notify(Notice.paused), author) is False
    assert mails(Notify(Notice.cancelled), signer) is False


def test__mark_requests__marks_only_requests_and_the_calculation_stops_repeating_them() -> None:
    route = _route()
    _, supervisor, academic = route.participants
    notices = (
        Notify(Notice.request, (supervisor.id,), outcome=RequestOutcome.approve),
        Notify(Notice.reminder, (academic.id,), outcome=RequestOutcome.approve),
        Notify(Notice.completed, (academic.id,), sender=True),
    )

    marked = mark_requests(route, notices, at=T0)

    assert marked.participant(supervisor.id).notified == Notified(round=2, outcome=RequestOutcome.approve, at=T0)
    assert marked.participant(academic.id).notified is None


def test__notices_in__keeps_only_notifications() -> None:
    notify = Notify(Notice.paused, sender=True)

    assert notices_in((Freeze("doc"), notify)) == (notify,)


def test__skipped__to_the_skipped_with_letter_never_to_the_one_who_skipped_himself() -> None:
    route = _route()
    author, _, academic = route.participants
    skipped = Notify(Notice.skipped, (academic.id,))
    who = Recipient(academic.user_id, academic.id)  # type: ignore[arg-type]

    by_author = recipients(route, skipped, actor_id=author.user_id)
    by_himself = recipients(route, skipped, actor_id=academic.user_id)

    assert [r.user_id for r in by_author] == [academic.user_id]
    assert by_himself == ()
    assert mails(skipped, who) is True
    assert dedupe_key(route, skipped, who) == f"signing:{route.id.hex}:2:{academic.id.hex}:signing_skipped"
