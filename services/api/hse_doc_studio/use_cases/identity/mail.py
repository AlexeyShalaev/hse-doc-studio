"""Доставка ссылок из писем: почтой, если настроен SMTP, иначе ссылкой на экране и записью в outbox."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.identity.entities import MailKind, MailOutboxEntry
from hse_doc_studio.core.identity.protocols import IMailOutboxRepository, IMailSender

_log = logging.getLogger(__name__)

# (тема, текст) для ru и en; {link} подставляется ссылкой.
_TEXTS: dict[MailKind, tuple[tuple[str, str], tuple[str, str]]] = {
    MailKind.verify_email: (
        (
            "Подтвердите e-mail",
            (
                "Чтобы подтвердить адрес, откройте ссылку:\n{link}\n\n"
                "Если вы не регистрировались, просто проигнорируйте письмо."
            ),
        ),
        (
            "Confirm your email",
            "Open this link to confirm your address:\n{link}\n\nIf you did not sign up, just ignore this message.",
        ),
    ),
    MailKind.reset_password: (
        (
            "Сброс пароля",
            (
                "Чтобы задать новый пароль, откройте ссылку:\n{link}\n\n"
                "Если вы не просили сброс, проигнорируйте письмо: пароль останется прежним."
            ),
        ),
        (
            "Password reset",
            (
                "Open this link to set a new password:\n{link}\n\n"
                "If you did not ask for a reset, ignore this message: your password stays the same."
            ),
        ),
    ),
    MailKind.invite: (
        ("Приглашение в Студию", "Вас пригласили в Студию. Чтобы зарегистрироваться, откройте ссылку:\n{link}"),
        ("Invitation to the Studio", "You are invited to the Studio. Open this link to sign up:\n{link}"),
    ),
    MailKind.email_change: (
        (
            "Подтвердите новый e-mail",
            (
                "Чтобы привязать этот адрес к учётной записи, откройте ссылку:\n{link}\n\n"
                "Если вы не меняли адрес, проигнорируйте письмо."
            ),
        ),
        (
            "Confirm your new email",
            (
                "Open this link to attach this address to your account:\n{link}\n\n"
                "If you did not change your address, ignore this message."
            ),
        ),
    ),
}

# Уведомления без ссылки.
_NOTICES: dict[MailKind, tuple[tuple[str, str], tuple[str, str]]] = {
    MailKind.reset_notice: (
        (
            "Администратор выдал ссылку для сброса пароля",
            (
                "Администратор Студии создал ссылку для сброса пароля вашей учётной записи. "
                "Если вы об этом не просили, свяжитесь с администратором."
            ),
        ),
        (
            "An administrator issued a password reset link",
            (
                "A Studio administrator created a password reset link for your account. "
                "If you did not ask for it, contact the administrator."
            ),
        ),
    ),
}


def auth_link(public_url: str | None, path: str, token: str) -> str:
    """Ссылка на страницу клиента: `<public_url>/<path>/<token>`."""
    base = (public_url or "").rstrip("/")
    return f"{base}{path}/{token}"


def _lang(locale: str | None) -> Lang:
    return Lang(locale) if locale in ("ru", "en") else current_interface_language()


class LinkDelivery:
    """Письмо уходит по SMTP; без SMTP или при сбое ссылка остаётся в outbox.

    Без SMTP ссылка возвращается вызывающему. С `background=True` отправка идёт отдельной задачей: запрос не ждёт
    SMTP (до его таймаута), а время ответа не выдаёт, существует ли адрес. Сбой такой отправки кладёт ссылку в
    outbox, вызывающему её уже не вернуть.
    """

    def __init__(
        self,
        sender: IMailSender,
        outbox: IMailOutboxRepository,
        ttl: timedelta = timedelta(days=7),
        *,
        background: bool = False,
    ) -> None:
        self._sender = sender
        self._outbox = outbox
        self._ttl = ttl
        self._background = background
        # Ссылки на задачи: цикл событий держит задачи слабо, и незавершённая отправка могла бы пропасть.
        self._pending: set[asyncio.Task[None]] = set()

    async def drain(self) -> None:
        """Дожидается отправок, начатых в фоне (остановка и тесты)."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    @property
    def smtp_enabled(self) -> bool:
        return self._sender.enabled

    async def deliver(
        self, kind: MailKind, to_email: str, link: str, now: datetime, *, locale: str | None = None
    ) -> str | None:
        """Ссылка для показа человеку (copyable) либо None, если письмо ушло.

        Язык письма: язык получателя, если он известен, иначе язык интерфейса запроса.
        """
        if self._sender.enabled:
            ru, en = _TEXTS[kind]
            subject, body = en if _lang(locale) is Lang.en else ru
            text = body.format(link=link)
            if self._background:
                task = asyncio.create_task(self._send_in_background(kind, to_email, link, now, subject, text))
                self._pending.add(task)
                task.add_done_callback(self._pending.discard)
                return None
            try:
                await self._sender.send(to_email, subject, text)
            except Exception:
                # Сбой почты не должен ломать регистрацию: человек получит ссылку другим путём.
                _log.warning("mail delivery failed, link kept in outbox", extra={"kind": kind.value})
            else:
                return None
        await self._keep_in_outbox(kind, to_email, link, now)
        return link

    async def _send_in_background(
        self, kind: MailKind, to_email: str, link: str, now: datetime, subject: str, text: str
    ) -> None:
        try:
            await self._sender.send(to_email, subject, text)
        except Exception:
            _log.warning("mail delivery failed, link kept in outbox", extra={"kind": kind.value})
            try:
                await self._keep_in_outbox(kind, to_email, link, now)
            except Exception:
                _log.exception("mail outbox write failed", extra={"kind": kind.value})

    async def _keep_in_outbox(self, kind: MailKind, to_email: str, link: str, now: datetime) -> None:
        await self._outbox.add(
            MailOutboxEntry(
                id=uuid.uuid4().hex,
                kind=kind,
                to_email=to_email,
                link=link,
                created_at=now,
                expires_at=now + self._ttl,
            )
        )

    async def notify(self, kind: MailKind, to_email: str, *, locale: str | None = None) -> bool:
        """Уведомление без ссылки; уходит только по SMTP, сбой не мешает действию, о котором уведомляют."""
        if not self._sender.enabled:
            return False
        ru, en = _NOTICES[kind]
        subject, body = en if _lang(locale) is Lang.en else ru
        try:
            await self._sender.send(to_email, subject, body)
        except Exception:
            _log.warning("mail notice failed", extra={"kind": kind.value})
            return False
        return True
