"""Письма уведомлений и приглашений в проект: язык, HTML, экранирование, ссылки и сбой SMTP."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.mail.journal import MailLinkKind, MailLogEntry, MailOrigin, MailSkipReason, MailStatus
from hse_doc_studio.infra.notifications.mailer import SmtpNotificationMailer
from hse_doc_studio.use_cases.mail.dispatch import MailCounters, MailDispatcher

from tests.fakes.mail_log import InMemoryMailLogRepository

SERVER = "https://studio.example.org"


class _Sender:
    def __init__(self, *, enabled: bool = True, fail: bool = False) -> None:
        self.enabled = enabled
        self.fail = fail
        self.sent: list[tuple[str, str, str, str | None]] = []

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> str:
        if self.fail:
            raise OSError("smtp down")
        self.sent.append((to, subject, body, html))
        return f"<{len(self.sent)}@fake.test>"


def _mailer(
    sender: _Sender, server: str | None = SERVER, log: InMemoryMailLogRepository | None = None
) -> SmtpNotificationMailer:
    dispatcher = MailDispatcher(sender, log or InMemoryMailLogRepository(), counters=MailCounters())
    return SmtpNotificationMailer(dispatcher, server)


def _payload(**kw: str) -> NotificationPayload:
    return NotificationPayload(project_name="Курсовая", actor_name="Анна", role="editor", **kw)


async def test__notification__ru_account_gets_a_russian_letter_with_html_and_inbox_link() -> None:
    sender = _Sender()

    ok = await _mailer(sender, SERVER).send_notification(
        "ann@example.org", NotificationKind.project_invitation, _payload(), locale="ru"
    )

    assert ok is True
    [(to, subject, body, html)] = sender.sent
    assert (to, subject) == ("ann@example.org", "Анна приглашает вас в «Курсовая»")
    assert f"{SERVER}/inbox" in body
    assert html is not None
    assert f'href="{SERVER}/inbox"' in html


async def test__notification__en_account_gets_an_english_letter() -> None:
    sender = _Sender()

    await _mailer(sender, SERVER).send_notification(
        "ann@example.org", NotificationKind.access_request, _payload(), locale="en"
    )

    assert sender.sent[0][1] == "Анна requests access to “Курсовая”"
    assert "Project access request" in (sender.sent[0][3] or "")


async def test__notification__names_are_escaped_in_html() -> None:
    sender = _Sender()
    payload = NotificationPayload(project_name="<b>X</b>", actor_name="A&B", role="reader")

    await _mailer(sender, SERVER).send_notification(
        "ann@example.org", NotificationKind.transfer_request, payload, locale="en"
    )

    html = sender.sent[0][3] or ""
    assert "<b>X</b>" not in html
    assert "&lt;b&gt;X&lt;/b&gt;" in html
    assert "A&amp;B" in html


async def test__notification__unmailed_kind_and_disabled_smtp_send_nothing() -> None:
    sender = _Sender()
    off = _Sender(enabled=False)

    unmailed = await _mailer(sender, SERVER).send_notification(
        "a@x.org", NotificationKind.member_removed, _payload(), locale="en"
    )
    disabled = await _mailer(off, SERVER).send_notification(
        "a@x.org", NotificationKind.project_invitation, _payload(), locale="en"
    )

    assert (unmailed, disabled) == (False, False)
    assert sender.sent == [] == off.sent


async def test__notification__smtp_failure_is_not_raised() -> None:
    ok = await _mailer(_Sender(fail=True), SERVER).send_notification(
        "a@x.org", NotificationKind.project_invitation, _payload(), locale="en"
    )

    assert ok is False


async def test__invitation_link__carries_message_role_expiry_and_the_link() -> None:
    sender = _Sender()

    ok = await _mailer(sender, SERVER).send_invitation(
        "new@example.org",
        project_name="ВКР",
        inviter_name="Анна",
        role="editor",
        link=f"{SERVER}/project-invite/tok",
        message="Привет\n<script>x</script>",
        locale=None,
        expires_at=datetime(2026, 11, 10, 14, 30, tzinfo=UTC),
    )

    assert ok is True
    [(_, subject, body, html)] = sender.sent
    assert subject == "Анна приглашает вас в «ВКР»"
    assert f"\n{SERVER}/project-invite/tok\n" in body
    assert "> Привет" in body
    assert "до 10.11.2026 14:30 UTC" in body
    assert html is not None
    assert "<script>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html
    assert f'href="{SERVER}/project-invite/tok"' in html


async def test__invitation_link__without_account_uses_the_inviter_language() -> None:
    from hse_doc_studio.core.i18n import set_interface_language

    sender = _Sender()
    set_interface_language("en")
    try:
        await _mailer(sender, SERVER).send_invitation(
            "new@example.org",
            project_name="Thesis",
            inviter_name="Anna",
            role="reader",
            link=f"{SERVER}/project-invite/tok",
            message=None,
            locale=None,
        )
    finally:
        set_interface_language(None)

    assert sender.sent[0][1] == "Anna invites you to “Thesis”"


async def test__notification__invitation_message_goes_into_the_letter_escaped() -> None:
    sender = _Sender()
    message = "Здравствуйте, Хади!\n\nПриглашаю вас <b>в проект</b> & жду."

    await _mailer(sender, SERVER).send_notification(
        "hadi@example.org", NotificationKind.project_invitation, _payload(excerpt=message), locale="ru"
    )

    [(_, _, body, html)] = sender.sent
    assert "> Здравствуйте, Хади!" in body
    assert "> Приглашаю вас <b>в проект</b> & жду." in body
    assert html is not None
    assert "<b>в проект</b>" not in html
    assert "&lt;b&gt;в проект&lt;/b&gt; &amp; жду." in html


async def test__notification__long_invitation_message_is_cut_and_other_kinds_ignore_excerpt() -> None:
    sender = _Sender()

    await _mailer(sender, SERVER).send_notification(
        "a@x.org", NotificationKind.project_invitation, _payload(excerpt="я" * 5000), locale="ru"
    )
    await _mailer(sender, SERVER).send_notification(
        "a@x.org", NotificationKind.access_request, _payload(excerpt="секретная выдержка"), locale="ru"
    )

    invitation_body, request_body = sender.sent[0][2], sender.sent[1][2]
    assert "я" * 999 in invitation_body
    assert "я" * 1001 not in invitation_body
    assert "секретная выдержка" not in request_body


# Маршрут подписания (docs/design/signing-route.md, 6.6): страница подписи подписанту, точка сдачи автору.

PROJECT = "5b0c1d2e-3f40-4152-8364-758697a8b9c0"
ROUTE = "0d1e2f30-4152-4637-8899-aabbccddeeff"


def _signing(**kw: str | None) -> NotificationPayload:
    base: dict[str, str | None] = {
        "project_id": PROJECT,
        "project_name": "Bertie",
        "actor_name": "Иван Иванов",
        "ref_id": ROUTE,
        "outcome": "approve",
        "excerpt": "Заявка на тему КП",
        "profile_id": "topic-approval",
        "deadline": "2026-11-15T20:59:00+00:00",
    }
    return NotificationPayload(**{**base, **kw})


async def test__signing_request__links_to_the_signing_page_with_point_and_deadline() -> None:
    mailer = _mailer(_Sender(), SERVER)

    mail = mailer.render_notification("p@x.org", NotificationKind.signing_request, _signing(), locale="ru")

    assert mail is not None
    assert mail.subject == "Иван Иванов просит подписать: Заявка на тему КП"
    assert f'href="{SERVER}/sign/{PROJECT}/{ROUTE}"' in mail.html
    assert "Срок: 15.11.2026 20:59 UTC" in mail.text
    assert "Контрольная точка: Заявка на тему КП" in mail.text


async def test__signing_request__sign_turn_asks_for_the_final_pdf_and_no_deadline_row_without_deadline() -> None:
    mailer = _mailer(_Sender(), SERVER)

    mail = mailer.render_notification(
        "p@x.org", NotificationKind.signing_request, _signing(outcome="sign", deadline=None), locale="en"
    )

    assert mail is not None
    assert mail.subject == "Sign the final PDF: Заявка на тему КП"
    assert "Deadline" not in mail.text


async def test__signing_request__new_version__changed_documents_and_sender_message() -> None:
    """12.6: письмо запроса новой версии называет изменившиеся документы и несёт сообщение автора."""
    mailer = _mailer(_Sender(), SERVER)
    payload = replace(_signing(message="Исправил тему", changed_names="«Заявление о выборе темы»"), new_version=True)

    mail = mailer.render_notification("p@x.org", NotificationKind.signing_request, payload, locale="ru")

    assert mail is not None
    assert mail.subject == "Иван Иванов просит подписать новую версию: Заявка на тему КП"
    assert "Изменились: «Заявление о выборе темы»" in mail.text
    assert "Сообщение автора" in mail.text
    assert "Исправил тему" in mail.text
    assert f'href="{SERVER}/sign/{PROJECT}/{ROUTE}"' in mail.html


async def test__signing_new_version__inbox_only() -> None:
    mailer = _mailer(_Sender(), SERVER)

    assert mailer.render_notification("p@x.org", NotificationKind.signing_new_version, _signing(), locale="ru") is None


async def test__signing_returned__comment_in_a_block_and_link_to_the_checkpoint() -> None:
    mailer = _mailer(_Sender(), SERVER)
    payload = _signing(outcome=None, actor_name="Пётр Петров", excerpt="Уточните <цель>")

    mail = mailer.render_notification("a@x.org", NotificationKind.signing_returned, payload, locale="ru")

    assert mail is not None
    assert mail.subject == "Документы возвращены на доработку: Пётр Петров"
    assert "Комментарий" in mail.text
    assert "Уточните <цель>" in mail.text
    assert "&lt;цель&gt;" in mail.html
    assert f'href="{SERVER}/projects/{PROJECT}/submit/cp/topic-approval"' in mail.html


async def test__signing_completed_and_reminder__render_and_paused_has_no_letter() -> None:
    mailer = _mailer(_Sender(), SERVER)

    completed = mailer.render_notification("a@x.org", NotificationKind.signing_completed, _signing(), locale="en")
    reminder = mailer.render_notification("p@x.org", NotificationKind.signing_reminder, _signing(), locale="en")
    paused = mailer.render_notification("a@x.org", NotificationKind.signing_paused, _signing(), locale="en")

    assert completed is not None
    assert completed.subject == "Everyone has signed: Заявка на тему КП"
    assert reminder is not None
    assert reminder.subject == "Reminder: Заявка на тему КП"
    assert f"{SERVER}/sign/{PROJECT}/{ROUTE}" in reminder.text
    assert paused is None


async def test__signing_mail__without_public_url_has_no_button_and_odd_ids_are_escaped() -> None:
    no_url = _mailer(_Sender(), None).render_notification(
        "p@x.org", NotificationKind.signing_request, _signing(), locale="ru"
    )
    odd = _mailer(_Sender(), SERVER).render_notification(
        "a@x.org", NotificationKind.signing_completed, _signing(profile_id="a/b c"), locale="ru"
    )

    assert no_url is not None
    assert "/sign/" not in no_url.text
    assert odd is not None
    assert f"{SERVER}/projects/{PROJECT}/submit/cp/a%2Fb%20c" in odd.text


# Журнал писем (docs/design/mail-log.md, P8..P14): каждая попытка оставляет одну строку через `MailDispatcher`.

INVITATION = "inv_0123456789abcdef"


def _row(log: InMemoryMailLogRepository) -> MailLogEntry:
    [entry] = log.entries
    return entry


async def test__journal__notification_row_has_the_page_object_and_no_message_text() -> None:
    log = InMemoryMailLogRepository()
    payload = _payload(project_id=PROJECT, ref_id=INVITATION, excerpt="личное сообщение приглашающего")

    ok = await _mailer(_Sender(), log=log).send_notification(
        "ann@example.org", NotificationKind.project_invitation, payload, locale="ru", to_user_id="u-ann"
    )

    entry = _row(log)
    assert ok is True
    assert (entry.template, entry.status, entry.origin) == ("project_invitation", MailStatus.sent, "notification")
    assert (entry.to_email, entry.to_user_id, entry.project_id) == ("ann@example.org", "u-ann", PROJECT)
    assert (entry.ref_kind, entry.ref_id) == ("project_invitation", INVITATION)
    assert entry.params.link is MailLinkKind.page
    assert entry.params.link_path == "/inbox"
    assert entry.params.values == {"actor": "Анна", "project": "Курсовая", "role": "editor"}
    assert entry.params.note_len == len("личное сообщение приглашающего")
    assert "личное сообщение" not in repr(entry)


@pytest.mark.parametrize(
    ("kind", "ref_kind"),
    [
        (NotificationKind.access_request, "access_request"),
        (NotificationKind.transfer_request, "transfer"),
    ],
)
async def test__journal__requests_point_at_their_object(kind: NotificationKind, ref_kind: str) -> None:
    log = InMemoryMailLogRepository()

    await _mailer(_Sender(), log=log).send_notification(
        "a@x.org", kind, _payload(project_id=PROJECT, ref_id="req-1"), locale="en"
    )

    entry = _row(log)
    assert (entry.ref_kind, entry.ref_id, entry.project_id) == (ref_kind, "req-1", PROJECT)
    assert entry.params.link_path == "/inbox"
    assert "role" not in entry.params.values


async def test__journal__signing_mail_keeps_the_page_path_and_without_public_url_no_link() -> None:
    log, bare = InMemoryMailLogRepository(), InMemoryMailLogRepository()

    await _mailer(_Sender(), log=log).send_notification(
        "p@x.org", NotificationKind.signing_reminder, _signing(), locale="ru"
    )
    await _mailer(_Sender(), None, log=bare).send_notification(
        "p@x.org", NotificationKind.signing_request, _signing(), locale="ru"
    )

    entry, no_url = _row(log), _row(bare)
    assert (entry.template, entry.ref_kind, entry.ref_id) == ("signing_reminder", "signing_route", ROUTE)
    assert entry.params.link is MailLinkKind.page
    assert entry.params.link_path == f"/sign/{PROJECT}/{ROUTE}"
    assert entry.params.server == SERVER
    assert no_url.params.link is MailLinkKind.none
    assert no_url.params.link_path is None


async def test__journal__smtp_failure_and_disabled_smtp_are_rows_too() -> None:
    failed_log, off_log = InMemoryMailLogRepository(), InMemoryMailLogRepository()
    off = _Sender(enabled=False)

    failed = await _mailer(_Sender(fail=True), log=failed_log).send_notification(
        "a@x.org", NotificationKind.project_invitation, _payload(), locale="en"
    )
    disabled = await _mailer(off, log=off_log).send_notification(
        "a@x.org", NotificationKind.project_invitation, _payload(), locale="en"
    )

    assert (failed, disabled) == (False, False)
    assert (_row(failed_log).status, _row(failed_log).reason) == (MailStatus.failed, "other")
    assert (_row(off_log).status, _row(off_log).reason) == (MailStatus.not_sent, "smtp_off")
    assert off.sent == []


async def test__journal__unmailed_kind_leaves_no_row_even_when_skipped() -> None:
    log = InMemoryMailLogRepository()
    mailer = _mailer(_Sender(), log=log)

    await mailer.send_notification("a@x.org", NotificationKind.member_removed, _payload(), locale="en")
    await mailer.skip_notification(
        "a@x.org", NotificationKind.signing_paused, _payload(), locale="en", reason=MailSkipReason.email_unverified
    )

    assert log.entries == []


async def test__journal__skipped_notification_is_suppressed_and_not_sent() -> None:
    log, sender = InMemoryMailLogRepository(), _Sender()

    await _mailer(sender, log=log).skip_notification(
        "a@x.org",
        NotificationKind.signing_reminder,
        _signing(),
        locale="ru",
        reason=MailSkipReason.account_blocked,
        to_user_id="u-a",
        origin=MailOrigin.signing_auto_reminder,
    )

    entry = _row(log)
    assert sender.sent == []
    assert (entry.status, entry.reason, entry.origin) == (
        MailStatus.suppressed,
        "account_blocked",
        "signing_auto_reminder",
    )
    assert (entry.to_user_id, entry.ref_kind) == ("u-a", "signing_route")


async def test__journal__invitation_link_token_is_not_kept() -> None:
    log, sender = InMemoryMailLogRepository(), _Sender()
    token = "SECRET-TOKEN-0123456789"

    ok = await _mailer(sender, log=log).send_invitation(
        "new@example.org",
        project_name="ВКР",
        inviter_name="Анна",
        role="editor",
        link=f"{SERVER}/project-invite/{token}?next=%2Fsign",
        message="Привет",
        locale="ru",
        expires_at=datetime(2026, 11, 10, 14, 30, tzinfo=UTC),
        origin=MailOrigin.signing_reinvite,
        to_user_id="u-new",
        project_id=PROJECT,
        invitation_id=INVITATION,
    )

    entry = _row(log)
    assert ok is True
    assert token in sender.sent[0][2]
    assert token not in repr(entry)
    assert (entry.template, entry.origin, entry.status) == ("project_invitation_link", "signing_reinvite", "sent")
    assert (entry.ref_kind, entry.ref_id, entry.project_id, entry.to_user_id) == (
        "project_invitation",
        INVITATION,
        PROJECT,
        "u-new",
    )
    assert entry.params.link is MailLinkKind.token
    assert entry.params.expires_at == datetime(2026, 11, 10, 14, 30, tzinfo=UTC)


async def test__journal__invitation_without_smtp_is_not_sent_and_answers_false() -> None:
    log = InMemoryMailLogRepository()

    ok = await _mailer(_Sender(enabled=False), log=log).send_invitation(
        "new@example.org",
        project_name="ВКР",
        inviter_name="Анна",
        role="reader",
        link=f"{SERVER}/project-invite/tok",
        message=None,
        locale=None,
    )

    entry = _row(log)
    assert ok is False
    assert (entry.status, entry.reason, entry.origin) == (MailStatus.not_sent, "smtp_off", "project_invite")
    assert entry.ref_kind is None
