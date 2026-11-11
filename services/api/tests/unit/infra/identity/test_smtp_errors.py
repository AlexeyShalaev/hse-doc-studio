"""Классы сбоев SMTP (docs/design/mail-log.md, L16): класс, код, текст без переводов строк и секретов."""

from __future__ import annotations

import base64
import socket
import ssl

import aiosmtplib
import pytest
from hse_doc_studio.core.mail.journal import ERROR_TEXT_MAX, SECRET_MASK, MailFailure, MailFailureClass
from hse_doc_studio.infra.identity.smtp_errors import classify

LOGIN = "mailer@studio.example.org"
PASSWORD = "S3cret-Pa55"  # noqa: S105 — значение теста, проверяем, что его нет в тексте


def _wrapped(outer: BaseException, cause: BaseException) -> BaseException:
    try:
        raise outer from cause
    except BaseException as exc:  # noqa: BLE001 — нужно исключение с причиной
        return exc


@pytest.mark.parametrize(
    ("exc", "reason", "code"),
    [
        (aiosmtplib.SMTPAuthenticationError(535, "5.7.8 Authentication failed"), MailFailureClass.auth, 535),
        (
            aiosmtplib.SMTPRecipientRefused(550, "5.1.1 User unknown", "x@y.org"),
            MailFailureClass.recipient_refused,
            550,
        ),
        (
            aiosmtplib.SMTPRecipientsRefused([aiosmtplib.SMTPRecipientRefused(550, "5.1.1 No such user", "x@y.org")]),
            MailFailureClass.recipient_refused,
            550,
        ),
        (aiosmtplib.SMTPSenderRefused(553, "5.7.1 Sender rejected", "a@b.org"), MailFailureClass.sender_refused, 553),
        (aiosmtplib.SMTPDataError(554, "5.7.1 Message rejected as spam"), MailFailureClass.data_refused, 554),
        (aiosmtplib.SMTPConnectResponseError(421, "Too many connections"), MailFailureClass.connect, 421),
        (
            aiosmtplib.SMTPConnectError("Error connecting to smtp.example.org on port 587"),
            MailFailureClass.connect,
            None,
        ),
        (aiosmtplib.SMTPConnectTimeoutError("Timed out connecting"), MailFailureClass.timeout, None),
        (aiosmtplib.SMTPReadTimeoutError("Timed out waiting for server response"), MailFailureClass.timeout, None),
        (TimeoutError(), MailFailureClass.timeout, None),
        (aiosmtplib.SMTPServerDisconnected("Unexpected EOF received"), MailFailureClass.disconnected, None),
        (aiosmtplib.SMTPNotSupported("SMTP STARTTLS extension not supported by server."), MailFailureClass.tls, None),
        (aiosmtplib.SMTPNotSupported("SMTP AUTH extension not supported by server."), MailFailureClass.auth, None),
        (ssl.SSLCertVerificationError("certificate verify failed"), MailFailureClass.tls, None),
        (
            _wrapped(aiosmtplib.SMTPConnectError("Error connecting"), ssl.SSLError("wrong version number")),
            MailFailureClass.tls,
            None,
        ),
        (ConnectionRefusedError(61, "Connection refused"), MailFailureClass.connect, None),
        (socket.gaierror(8, "nodename nor servname provided"), MailFailureClass.connect, None),
        (aiosmtplib.SMTPHeloError(501, "Syntax error"), MailFailureClass.other, 501),
        (ValueError("something else"), MailFailureClass.other, None),
    ],
)
def test__classify__maps_exceptions_to_classes(exc: BaseException, reason: MailFailureClass, code: int | None) -> None:
    failure = classify(exc)

    assert (failure.reason, failure.smtp_code) == (reason, code)


def test__classify__text_is_the_server_reply_not_the_tuple() -> None:
    failure = classify(aiosmtplib.SMTPRecipientRefused(550, "5.1.1 User unknown", "x@y.org"))

    assert failure == MailFailure(reason=MailFailureClass.recipient_refused, smtp_code=550, text="5.1.1 User unknown")


def test__classify__unknown_error_names_its_type() -> None:
    assert classify(ValueError("something else")).text == "ValueError: something else"


def test__classify__hides_login_and_password_in_any_case_and_in_base64() -> None:
    plain = base64.b64encode(f"\0{LOGIN}\0{PASSWORD}".encode()).decode()
    login64 = base64.b64encode(LOGIN.encode()).decode()
    reply = f"5.7.8 {LOGIN.upper()} with {PASSWORD} rejected; got {plain} and {login64}"

    failure = classify(aiosmtplib.SMTPAuthenticationError(535, reply), secrets=(LOGIN, PASSWORD))

    assert failure.text is not None
    for secret in (LOGIN, LOGIN.upper(), PASSWORD, plain, login64):
        assert secret not in failure.text
    assert failure.text.count(SECRET_MASK) == 4  # noqa: PLR2004


def test__classify__no_line_breaks_and_at_most_300_characters() -> None:
    reply = "5.7.1 first line\r\n5.7.1 second\tline\n" + "z" * 1000

    failure = classify(aiosmtplib.SMTPDataError(554, reply), secrets=(None, ""))

    assert failure.text is not None
    assert failure.text.startswith("5.7.1 first line 5.7.1 second line z")
    assert "\n" not in failure.text
    assert "\r" not in failure.text
    assert len(failure.text) <= ERROR_TEXT_MAX


def test__classify__empty_text_is_none() -> None:
    assert classify(TimeoutError()).text is None
