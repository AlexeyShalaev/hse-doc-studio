"""Классы сбоев SMTP для журнала писем (docs/design/mail-log.md, L16).

`classify` превращает исключение `aiosmtplib` (или `ssl`, `OSError`) в `MailFailure`: класс для понятной подсказки
на экране, код ответа SMTP и очищенный текст для письма провайдеру. Логин и пароль SMTP в тексте заменяются на
«[скрыто]», в том числе в base64, как они ходят в `AUTH PLAIN` и `AUTH LOGIN`.
"""

from __future__ import annotations

import base64
import ssl
from collections.abc import Iterable, Iterator

import aiosmtplib

from hse_doc_studio.core.mail.journal import MailFailure, MailFailureClass, clean_error_text

# Порядок важен: `SMTPConnectTimeoutError` это и таймаут, и `SMTPConnectError`; `SMTPServerDisconnected` и
# таймауты это `OSError`; `SMTPConnectResponseError` это ответ сервера при соединении.
_CLASSES: tuple[tuple[type[BaseException] | tuple[type[BaseException], ...], MailFailureClass], ...] = (
    (aiosmtplib.SMTPAuthenticationError, MailFailureClass.auth),
    (aiosmtplib.SMTPRecipientRefused, MailFailureClass.recipient_refused),
    (aiosmtplib.SMTPSenderRefused, MailFailureClass.sender_refused),
    (aiosmtplib.SMTPDataError, MailFailureClass.data_refused),
    (aiosmtplib.SMTPConnectResponseError, MailFailureClass.connect),
    ((aiosmtplib.SMTPTimeoutError, TimeoutError), MailFailureClass.timeout),
    (aiosmtplib.SMTPServerDisconnected, MailFailureClass.disconnected),
    (aiosmtplib.SMTPResponseException, MailFailureClass.other),
    # Отказ в соединении, неизвестный хост (gaierror), сеть недоступна.
    ((aiosmtplib.SMTPConnectError, OSError), MailFailureClass.connect),
)


def _chain(exc: BaseException) -> Iterator[BaseException]:
    """Исключение и его причины: aiosmtplib заворачивает ошибку TLS в `SMTPConnectError`."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _secret_variants(secrets: Iterable[str | None]) -> list[str]:
    plain = [secret for secret in secrets if secret]
    variants = plain + [base64.b64encode(secret.encode("utf-8")).decode("ascii") for secret in plain]
    if len(plain) == 2:  # noqa: PLR2004 — логин и пароль: так их кодирует AUTH PLAIN
        login, password = plain
        variants.append(base64.b64encode(f"\0{login}\0{password}".encode()).decode("ascii"))
    return variants


def _text(exc: BaseException) -> str:
    message = getattr(exc, "message", None)
    return message if isinstance(message, str) and message else str(exc)


def _not_supported(exc: aiosmtplib.SMTPNotSupported) -> MailFailureClass:
    """«STARTTLS extension not supported», «SMTP AUTH extension not supported»: настройки не совпали с сервером."""
    lowered = str(exc).lower()
    if "tls" in lowered:
        return MailFailureClass.tls
    return MailFailureClass.auth if "auth" in lowered else MailFailureClass.other


def _classify_plain(exc: BaseException) -> tuple[MailFailureClass, int | None, BaseException]:
    """Класс, код SMTP и исключение, текст которого пойдёт в журнал."""
    if isinstance(exc, aiosmtplib.SMTPRecipientsRefused):
        refused = exc.recipients[0] if exc.recipients else None
        return MailFailureClass.recipient_refused, refused.code if refused else None, refused or exc
    code = exc.code if isinstance(exc, aiosmtplib.SMTPResponseException) else None
    if isinstance(exc, aiosmtplib.SMTPNotSupported):
        return _not_supported(exc), None, exc
    if not isinstance(exc, aiosmtplib.SMTPResponseException) and any(
        isinstance(link, ssl.SSLError) for link in _chain(exc)
    ):
        return MailFailureClass.tls, None, exc
    failure_class = next((cls for kind, cls in _CLASSES if isinstance(exc, kind)), MailFailureClass.other)
    return failure_class, code, exc


def classify(exc: BaseException, *, secrets: Iterable[str | None] = ()) -> MailFailure:
    """Сбой отправки как `MailFailure`; `secrets` это логин и пароль SMTP, их нет в тексте ни в каком виде."""
    failure_class, code, source = _classify_plain(exc)
    text = _text(source)
    if failure_class is MailFailureClass.other and not isinstance(source, aiosmtplib.SMTPException):
        text = f"{type(source).__name__}: {text}" if text else type(source).__name__
    return MailFailure(
        reason=failure_class,
        smtp_code=code if isinstance(code, int) and 0 < code < 1000 else None,  # noqa: PLR2004
        text=clean_error_text(text, secrets=_secret_variants(secrets)),
    )
