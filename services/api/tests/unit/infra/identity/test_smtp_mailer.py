from __future__ import annotations

import asyncio
import socket
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser

import aiosmtplib
import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword
from hse_doc_studio.core.identity.entities import MailKind
from hse_doc_studio.core.mail.journal import MailFailureClass, MailSendError
from hse_doc_studio.infra.identity.smtp_mailer import SmtpMailSender, SmtpSettings
from hse_doc_studio.use_cases.identity.mail import LinkDelivery

from tests.fakes.auth import InMemoryMailOutboxRepository

# aiosmtpd по умолчанию зовёт socket.getfqdn() (обратный DNS, на раннерах macOS висит), поэтому
# имя сервера задано явно; запас на старт потока нужен медленным раннерам.
_READY_S = 30.0


class _Inbox:
    def __init__(self) -> None:
        self.messages: list = []

    async def handle_DATA(self, server, session, envelope):  # type: ignore[no-untyped-def]  # noqa: N802, ANN001, ARG002
        self.messages.append(envelope)
        return "250 OK"


def _authenticator(server, session, envelope, mechanism, auth_data):  # type: ignore[no-untyped-def]  # noqa: ANN001, ARG001
    ok = isinstance(auth_data, LoginPassword) and auth_data.login == b"mailer" and auth_data.password == b"s3cret"
    return AuthResult(success=ok, handled=False)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def inbox() -> Iterator[tuple[_Inbox, int]]:
    handler = _Inbox()
    port = _free_port()
    controller = Controller(
        handler, hostname="127.0.0.1", port=port, server_hostname="localhost", ready_timeout=_READY_S
    )
    controller.start()
    yield handler, port
    controller.stop()


@pytest.fixture
def auth_inbox() -> Iterator[tuple[_Inbox, int]]:
    handler = _Inbox()
    port = _free_port()
    controller = Controller(
        handler,
        hostname="127.0.0.1",
        port=port,
        server_hostname="localhost",
        ready_timeout=_READY_S,
        authenticator=_authenticator,
        auth_required=True,
        auth_require_tls=False,
    )
    controller.start()
    yield handler, port
    controller.stop()


def _settings(port: int, **kw: object) -> SmtpSettings:
    return SmtpSettings(host="127.0.0.1", port=port, security="none", **kw)  # type: ignore[arg-type]


async def test_sends_a_plain_text_message(inbox: tuple[_Inbox, int]) -> None:
    handler, port = inbox
    sender = SmtpMailSender(_settings(port, from_address="studio@example.org", from_name="Студия"))

    message_id = await sender.send("anna@example.org", "Сброс пароля", "Откройте ссылку: https://studio.test/reset/abc")

    assert sender.enabled
    (envelope,) = handler.messages
    assert message_id.startswith("<")
    assert message_id.endswith("@example.org>")
    assert _parse(envelope.content)["Message-ID"] == message_id
    assert envelope.mail_from == "studio@example.org"
    assert envelope.rcpt_tos == ["anna@example.org"]
    text = envelope.content.decode("utf-8")
    assert "To: anna@example.org" in text
    assert "Auto-Submitted: auto-generated" in text
    assert "https://studio.test/reset/abc" in text


async def test_authenticates_with_login_and_password(auth_inbox: tuple[_Inbox, int]) -> None:
    handler, port = auth_inbox
    sender = SmtpMailSender(_settings(port, username="mailer", password="s3cret"))

    await sender.send("anna@example.org", "Тема", "Текст")

    assert len(handler.messages) == 1


async def test_wrong_password_raises(auth_inbox: tuple[_Inbox, int]) -> None:
    handler, port = auth_inbox
    sender = SmtpMailSender(_settings(port, username="mailer", password="wrong-pass"))

    with pytest.raises(MailSendError) as exc:
        await sender.send("anna@example.org", "Тема", "Текст")

    assert handler.messages == []
    failure = exc.value.failure
    assert (failure.reason, failure.smtp_code) == (MailFailureClass.auth, 535)
    assert isinstance(exc.value.__cause__, aiosmtplib.SMTPAuthenticationError)
    assert "wrong-pass" not in (failure.text or "")


async def test_missing_credentials_are_refused_by_a_server_that_requires_them(
    auth_inbox: tuple[_Inbox, int],
) -> None:
    _, port = auth_inbox
    with pytest.raises(MailSendError) as exc:
        await SmtpMailSender(_settings(port)).send("anna@example.org", "Тема", "Текст")
    assert exc.value.failure.smtp_code == 530


async def test_silent_server_times_out() -> None:
    async def silent(_reader: asyncio.StreamReader, _writer: asyncio.StreamWriter) -> None:
        await asyncio.sleep(30)

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    sender = SmtpMailSender(_settings(port, timeout_s=0.3))
    try:
        with pytest.raises(MailSendError) as exc:
            await sender.send("anna@example.org", "Тема", "Текст")
        assert exc.value.failure.reason is MailFailureClass.timeout
    finally:
        server.close()


async def test_refused_connection_raises() -> None:
    with pytest.raises(MailSendError) as exc:
        await SmtpMailSender(_settings(_free_port(), timeout_s=1)).send("anna@example.org", "Тема", "Текст")
    assert exc.value.failure.reason is MailFailureClass.connect


def _parse(raw: bytes) -> EmailMessage:
    message = BytesParser(policy=policy.default).parsebytes(raw)
    assert isinstance(message, EmailMessage)
    return message


async def test_html_makes_a_multipart_alternative_with_text_first(inbox: tuple[_Inbox, int]) -> None:
    handler, port = inbox
    sender = SmtpMailSender(_settings(port, from_address="studio@example.org", from_name="Студия"))

    await sender.send(
        "anna@example.org", "Сброс пароля", "Текст письма\nhttps://studio.test/reset/abc", html="<p>HTML</p>"
    )

    message = _parse(handler.messages[0].content)
    assert message.get_content_type() == "multipart/alternative"
    assert [part.get_content_type() for part in message.iter_parts()] == ["text/plain", "text/html"]
    text, html = message.iter_parts()
    assert "https://studio.test/reset/abc" in text.get_content()
    assert html.get_content().strip() == "<p>HTML</p>"
    assert text.get_content_charset() == "utf-8"
    assert html.get_content_charset() == "utf-8"
    assert message["Subject"] == "Сброс пароля"
    assert message["Auto-Submitted"] == "auto-generated"


async def test_without_html_the_message_stays_plain_text(inbox: tuple[_Inbox, int]) -> None:
    handler, port = inbox

    await SmtpMailSender(_settings(port)).send("anna@example.org", "Тема", "Текст")

    message = _parse(handler.messages[0].content)
    assert message.get_content_type() == "text/plain"
    assert not message.is_multipart()


async def test_line_breaks_in_the_subject_do_not_add_headers(inbox: tuple[_Inbox, int]) -> None:
    handler, port = inbox

    await SmtpMailSender(_settings(port)).send("anna@example.org", "Тема\r\nBcc: evil@example.org", "Текст")

    message = _parse(handler.messages[0].content)
    assert message["Bcc"] is None
    assert message["Subject"] == "Тема Bcc: evil@example.org"


@pytest.mark.parametrize(
    ("locale", "subject", "needle"),
    [("en", "Password reset", "Set a new password"), ("ru", "Сброс пароля", "Задать новый пароль")],
)
async def test_delivery_over_smtp_sends_a_localized_multipart_letter(
    inbox: tuple[_Inbox, int], locale: str, subject: str, needle: str
) -> None:
    handler, port = inbox
    delivery = LinkDelivery(
        SmtpMailSender(_settings(port, from_address="studio@example.org")),
        InMemoryMailOutboxRepository(),
        public_url="https://studio.example.org",
    )

    shown = await delivery.deliver(
        MailKind.reset_password,
        "anna@example.org",
        "https://studio.example.org/reset/tok123",
        datetime(2026, 11, 3, tzinfo=UTC),
        locale=locale,
        ttl=timedelta(hours=1),
    )

    assert shown is None
    message = _parse(handler.messages[0].content)
    assert message["Subject"] == subject
    assert message["To"] == "anna@example.org"
    text, html = message.iter_parts()
    assert "https://studio.example.org/reset/tok123" in text.get_content()
    assert needle in html.get_content()
    assert 'href="https://studio.example.org/reset/tok123"' in html.get_content()
