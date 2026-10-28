from __future__ import annotations

import asyncio
import socket
from collections.abc import Iterator

import aiosmtplib
import pytest
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import AuthResult, LoginPassword
from hse_doc_studio.infra.identity.smtp_mailer import SmtpMailSender, SmtpSettings


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
    controller = Controller(handler, hostname="127.0.0.1", port=port)
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

    await sender.send("anna@example.org", "Сброс пароля", "Откройте ссылку: https://studio.test/reset/abc")

    assert sender.enabled
    (envelope,) = handler.messages
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
    sender = SmtpMailSender(_settings(port, username="mailer", password="wrong"))

    with pytest.raises(aiosmtplib.SMTPException):
        await sender.send("anna@example.org", "Тема", "Текст")

    assert handler.messages == []


async def test_missing_credentials_are_refused_by_a_server_that_requires_them(
    auth_inbox: tuple[_Inbox, int],
) -> None:
    _, port = auth_inbox
    with pytest.raises(aiosmtplib.SMTPException):
        await SmtpMailSender(_settings(port)).send("anna@example.org", "Тема", "Текст")


async def test_silent_server_times_out() -> None:
    async def silent(_reader: asyncio.StreamReader, _writer: asyncio.StreamWriter) -> None:
        await asyncio.sleep(30)

    server = await asyncio.start_server(silent, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    sender = SmtpMailSender(_settings(port, timeout_s=0.3))
    try:
        with pytest.raises((aiosmtplib.SMTPException, TimeoutError)):
            await sender.send("anna@example.org", "Тема", "Текст")
    finally:
        server.close()


async def test_refused_connection_raises() -> None:
    with pytest.raises((aiosmtplib.SMTPException, OSError)):
        await SmtpMailSender(_settings(_free_port(), timeout_s=1)).send("anna@example.org", "Тема", "Текст")
