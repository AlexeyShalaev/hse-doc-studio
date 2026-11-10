"""Доставка уведомлений маршрута: подписи, ключ повтора и письма по видам (docs/design/signing-route.md, 6.6)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from hse_doc_studio.core.invitations.entities import NotificationKind
from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.engine import notice_for
from hse_doc_studio.core.signing_route.entities import Notice, RequestOutcome, RouteStatus, StopReason
from hse_doc_studio.core.signing_route.notices import notices_in
from hse_doc_studio.core.signing_route.ports import RouteLabels
from hse_doc_studio.use_cases.signing_route.delivery import SigningNotifier

from tests.fakes.signing_routes import StaticRouteContext
from tests.unit.core.signing_route.world import T0
from tests.unit.use_cases.signing_route.helpers import PROFILE_NAME, Inbox, context, people, three_steps


async def test__send__request_goes_to_the_next_step_with_sender_point_and_deadline() -> None:
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    driver.route = replace(driver.route, deadline=T0 + timedelta(days=5))
    evaluation = driver.send(author.user_id)  # type: ignore[arg-type]
    inbox = Inbox()

    await SigningNotifier(inbox, people(driver.route), context(driver)).notify(
        driver.route, notices_in(evaluation.effects)
    )

    [sent] = inbox.sent
    route = driver.route
    assert (sent.user_id, sent.kind, sent.mail) == (supervisor.user_id.hex, NotificationKind.signing_request, True)  # type: ignore[union-attr]
    assert sent.dedupe_key == f"signing:{route.id.hex}:1:{supervisor.id.hex}:signing_request:approve"
    p = sent.payload
    assert (p.project_id, p.project_name, p.ref_id, p.profile_id) == (
        str(route.project_id),
        "Bertie",
        str(route.id),
        "topic-approval",
    )
    assert (p.actor_name, p.outcome, p.excerpt) == ("Иван", "approve", "Заявка на тему КП")
    assert p.deadline == (T0 + timedelta(days=5)).isoformat()


async def test__request__point_name_in_the_recipient_language() -> None:
    driver = three_steps()
    author, _, academic = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    inbox = Inbox()

    await SigningNotifier(inbox, people(driver.route), context(driver)).notify(
        driver.route, [Notify(Notice.request, (academic.id,), outcome=RequestOutcome.sign)]
    )

    [sent] = inbox.sent
    assert (sent.payload.excerpt, sent.payload.outcome) == ("Topic application", "sign")
    assert sent.dedupe_key is not None
    assert sent.dedupe_key.endswith(":signing_request:sign")


async def test__returned__comment_to_author_and_approvers_letter_only_to_the_author() -> None:
    driver = three_steps()
    author, supervisor, academic = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    driver.act(supervisor.id)
    route = replace(driver.route, status=RouteStatus.returned, stop_reason=StopReason.returned, stopped_by=academic.id)
    inbox = Inbox()

    await SigningNotifier(inbox, people(route), context(driver)).notify(
        route, [notice_for(route, Notice.returned)], actor_id=academic.user_id, comment="  Уточните цель  "
    )

    by_user = {s.user_id: s for s in inbox.sent}
    assert set(by_user) == {author.user_id.hex, supervisor.user_id.hex}  # type: ignore[union-attr]
    assert by_user[author.user_id.hex].mail is True  # type: ignore[union-attr]
    assert by_user[supervisor.user_id.hex].mail is False  # type: ignore[union-attr]
    payload = by_user[author.user_id.hex].payload  # type: ignore[union-attr]
    assert (payload.actor_name, payload.excerpt, payload.outcome) == ("Sam", "Уточните цель", None)


async def test__paused__reason_in_outcome_no_letter_and_completed_letter_to_author_only() -> None:
    driver = three_steps()
    author, supervisor, academic = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    paused = replace(driver.route, status=RouteStatus.paused, stop_reason=StopReason.rebuilt)
    inbox = Inbox()
    notifier = SigningNotifier(inbox, people(paused), context(driver))

    await notifier.notify(paused, [notice_for(paused, Notice.paused)])
    await notifier.notify(driver.route, [notice_for(driver.route, Notice.completed)])

    [pause, *done] = inbox.sent
    assert (pause.kind, pause.user_id, pause.payload.outcome, pause.mail) == (
        NotificationKind.signing_paused,
        author.user_id.hex,  # type: ignore[union-attr]
        "rebuilt",
        False,
    )
    assert pause.dedupe_key == f"signing:{paused.id.hex}:1:{author.id.hex}:signing_paused"
    assert [(s.user_id, s.mail) for s in done] == [
        (author.user_id.hex, True),  # type: ignore[union-attr]
        (supervisor.user_id.hex, False),  # type: ignore[union-attr]
        (academic.user_id.hex, False),  # type: ignore[union-attr]
    ]


async def test__reminder__outcome_of_the_last_request_and_unknown_project_still_delivers() -> None:
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    inbox = Inbox()
    ctx = context(driver)
    ctx.projects = {}

    await SigningNotifier(inbox, people(driver.route), ctx).notify(
        driver.route, [Notify(Notice.reminder, (supervisor.id,))]
    )

    [sent] = inbox.sent
    assert (sent.kind, sent.payload.outcome, sent.mail) == (NotificationKind.signing_reminder, "approve", True)
    assert (sent.payload.project_name, sent.payload.excerpt) == (None, "topic-approval")


async def test__cancelled__not_to_the_one_who_cancelled_and_nothing_for_no_notices() -> None:
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    cancelled = replace(driver.route, status=RouteStatus.cancelled, phase=None)
    inbox = Inbox()
    notifier = SigningNotifier(inbox, people(cancelled), context(driver))

    await notifier.notify(cancelled, [notice_for(cancelled, Notice.cancelled)], actor_id=author.user_id)
    await notifier.notify(cancelled, [])

    assert [(s.user_id, s.kind, s.mail, s.payload.actor_name) for s in inbox.sent] == [
        (supervisor.user_id.hex, NotificationKind.signing_cancelled, False, "Иван")  # type: ignore[union-attr]
    ]


async def test__request__new_version_round__flag_message_and_changed_names_for_the_mail() -> None:
    """12.6: запрос раунда новой версии помечен `new_version`, письму нужны сообщение и изменившиеся документы."""
    driver = three_steps()
    author, supervisor, _ = driver.route.participants
    driver.send(author.user_id)  # type: ignore[arg-type]
    doc_id = driver.route.docs[0]
    seen = driver.route.snapshot[doc_id]
    driver.route = replace(
        driver.route,
        message="Исправил тему",
        snapshot={**driver.route.snapshot, doc_id: replace(seen, replaced=True, sent_at=driver.route.sent_at)},
    )
    names = RouteLabels("Bertie", PROFILE_NAME, doc_names={doc_id: {"ru": "Заявление", "en": "Application"}})
    labels = StaticRouteContext(projects={driver.route.project_id: names})
    inbox = Inbox()

    await SigningNotifier(inbox, people(driver.route), labels).notify(
        driver.route,
        [
            Notify(Notice.request, (supervisor.id,), outcome=RequestOutcome.approve),
            Notify(Notice.new_version, (author.id,)),
        ],
        actor_id=None,
    )

    request, new_version = inbox.sent
    assert (request.payload.new_version, request.payload.message, request.payload.changed_names) == (
        True,
        "Исправил тему",
        "«Заявление»",
    )
    assert (new_version.kind, new_version.mail, new_version.payload.new_version) == (
        NotificationKind.signing_new_version,
        False,
        False,
    )
    assert new_version.payload.actor_name == "Иван"
