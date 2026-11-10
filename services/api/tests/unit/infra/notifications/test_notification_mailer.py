"""Письма уведомлений и приглашений в проект: язык, HTML, экранирование, ссылки и сбой SMTP."""

from __future__ import annotations

from datetime import UTC, datetime

from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.infra.notifications.mailer import SmtpNotificationMailer

SERVER = "https://studio.example.org"


class _Sender:
    def __init__(self, *, enabled: bool = True, fail: bool = False) -> None:
        self.enabled = enabled
        self.fail = fail
        self.sent: list[tuple[str, str, str, str | None]] = []

    async def send(self, to: str, subject: str, body: str, *, html: str | None = None) -> None:
        if self.fail:
            raise OSError("smtp down")
        self.sent.append((to, subject, body, html))


def _payload(**kw: str) -> NotificationPayload:
    return NotificationPayload(project_name="Курсовая", actor_name="Анна", role="editor", **kw)


async def test__notification__ru_account_gets_a_russian_letter_with_html_and_inbox_link() -> None:
    sender = _Sender()

    ok = await SmtpNotificationMailer(sender, SERVER).send_notification(
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

    await SmtpNotificationMailer(sender, SERVER).send_notification(
        "ann@example.org", NotificationKind.access_request, _payload(), locale="en"
    )

    assert sender.sent[0][1] == "Анна requests access to “Курсовая”"
    assert "Project access request" in (sender.sent[0][3] or "")


async def test__notification__names_are_escaped_in_html() -> None:
    sender = _Sender()
    payload = NotificationPayload(project_name="<b>X</b>", actor_name="A&B", role="reader")

    await SmtpNotificationMailer(sender, SERVER).send_notification(
        "ann@example.org", NotificationKind.transfer_request, payload, locale="en"
    )

    html = sender.sent[0][3] or ""
    assert "<b>X</b>" not in html
    assert "&lt;b&gt;X&lt;/b&gt;" in html
    assert "A&amp;B" in html


async def test__notification__unmailed_kind_and_disabled_smtp_send_nothing() -> None:
    sender = _Sender()
    off = _Sender(enabled=False)

    unmailed = await SmtpNotificationMailer(sender, SERVER).send_notification(
        "a@x.org", NotificationKind.member_removed, _payload(), locale="en"
    )
    disabled = await SmtpNotificationMailer(off, SERVER).send_notification(
        "a@x.org", NotificationKind.project_invitation, _payload(), locale="en"
    )

    assert (unmailed, disabled) == (False, False)
    assert sender.sent == [] == off.sent


async def test__notification__smtp_failure_is_not_raised() -> None:
    ok = await SmtpNotificationMailer(_Sender(fail=True), SERVER).send_notification(
        "a@x.org", NotificationKind.project_invitation, _payload(), locale="en"
    )

    assert ok is False


async def test__invitation_link__carries_message_role_expiry_and_the_link() -> None:
    sender = _Sender()

    ok = await SmtpNotificationMailer(sender, SERVER).send_invitation(
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
        await SmtpNotificationMailer(sender, SERVER).send_invitation(
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

    await SmtpNotificationMailer(sender, SERVER).send_notification(
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

    await SmtpNotificationMailer(sender, SERVER).send_notification(
        "a@x.org", NotificationKind.project_invitation, _payload(excerpt="я" * 5000), locale="ru"
    )
    await SmtpNotificationMailer(sender, SERVER).send_notification(
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
    mailer = SmtpNotificationMailer(_Sender(), SERVER)

    mail = mailer.render_notification("p@x.org", NotificationKind.signing_request, _signing(), locale="ru")

    assert mail is not None
    assert mail.subject == "Иван Иванов просит подписать: Заявка на тему КП"
    assert f'href="{SERVER}/sign/{PROJECT}/{ROUTE}"' in mail.html
    assert "Срок: 15.11.2026 20:59 UTC" in mail.text
    assert "Контрольная точка: Заявка на тему КП" in mail.text


async def test__signing_request__sign_turn_asks_for_the_final_pdf_and_no_deadline_row_without_deadline() -> None:
    mailer = SmtpNotificationMailer(_Sender(), SERVER)

    mail = mailer.render_notification(
        "p@x.org", NotificationKind.signing_request, _signing(outcome="sign", deadline=None), locale="en"
    )

    assert mail is not None
    assert mail.subject == "Sign the final PDF: Заявка на тему КП"
    assert "Deadline" not in mail.text


async def test__signing_returned__comment_in_a_block_and_link_to_the_checkpoint() -> None:
    mailer = SmtpNotificationMailer(_Sender(), SERVER)
    payload = _signing(outcome=None, actor_name="Пётр Петров", excerpt="Уточните <цель>")

    mail = mailer.render_notification("a@x.org", NotificationKind.signing_returned, payload, locale="ru")

    assert mail is not None
    assert mail.subject == "Документы возвращены на доработку: Пётр Петров"
    assert "Комментарий" in mail.text
    assert "Уточните <цель>" in mail.text
    assert "&lt;цель&gt;" in mail.html
    assert f'href="{SERVER}/projects/{PROJECT}/submit/cp/topic-approval"' in mail.html


async def test__signing_completed_and_reminder__render_and_paused_has_no_letter() -> None:
    mailer = SmtpNotificationMailer(_Sender(), SERVER)

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
    no_url = SmtpNotificationMailer(_Sender(), None).render_notification(
        "p@x.org", NotificationKind.signing_request, _signing(), locale="ru"
    )
    odd = SmtpNotificationMailer(_Sender(), SERVER).render_notification(
        "a@x.org", NotificationKind.signing_completed, _signing(profile_id="a/b c"), locale="ru"
    )

    assert no_url is not None
    assert "/sign/" not in no_url.text
    assert odd is not None
    assert f"{SERVER}/projects/{PROJECT}/submit/cp/a%2Fb%20c" in odd.text
