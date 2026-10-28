"""Доставка ссылок из писем: почтой, если настроен SMTP, иначе ссылкой на экране и записью в outbox."""

from __future__ import annotations

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
        ("Подтвердите e-mail", "Чтобы подтвердить адрес, откройте ссылку: {link}"),
        ("Confirm your email", "Open this link to confirm your address: {link}"),
    ),
    MailKind.reset_password: (
        ("Сброс пароля", "Чтобы задать новый пароль, откройте ссылку: {link}"),
        ("Password reset", "Open this link to set a new password: {link}"),
    ),
    MailKind.invite: (
        ("Приглашение в Студию", "Вас пригласили в Студию. Чтобы зарегистрироваться, откройте ссылку: {link}"),
        ("Invitation to the Studio", "You are invited to the Studio. Open this link to sign up: {link}"),
    ),
}


def auth_link(public_url: str | None, path: str, token: str) -> str:
    base = (public_url or "").rstrip("/")
    return f"{base}{path}?token={token}"


class LinkDelivery:
    """Письмо уходит по SMTP; без SMTP или при сбое ссылка остаётся в outbox и возвращается вызывающему."""

    def __init__(self, sender: IMailSender, outbox: IMailOutboxRepository, ttl: timedelta = timedelta(days=7)) -> None:
        self._sender = sender
        self._outbox = outbox
        self._ttl = ttl

    @property
    def smtp_enabled(self) -> bool:
        return self._sender.enabled

    async def deliver(self, kind: MailKind, to_email: str, link: str, now: datetime) -> str | None:
        """Ссылка для показа человеку (copyable) либо None, если письмо ушло."""
        if self._sender.enabled:
            ru, en = _TEXTS[kind]
            subject, body = en if current_interface_language() is Lang.en else ru
            try:
                await self._sender.send(to_email, subject, body.format(link=link))
            except Exception:
                # Сбой почты не должен ломать регистрацию: человек получит ссылку другим путём.
                _log.warning("mail delivery failed, link kept in outbox", extra={"kind": kind.value})
            else:
                return None
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
        return link
