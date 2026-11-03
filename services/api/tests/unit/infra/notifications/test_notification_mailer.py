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
