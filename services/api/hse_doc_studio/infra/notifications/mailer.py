"""Письма трека invites: приглашение в проект, запрос доступа, передача владения (ru и en).

В письме только подписи из уведомления и ссылка на «Входящие» или на страницу приглашения: секретов там нет,
кроме токена ссылки приглашения, который адресат и должен получить. Сбой SMTP действию не мешает.
Тексты и вёрстка лежат в `core.mail`.
"""

from __future__ import annotations

import logging
from datetime import datetime

from hse_doc_studio.core.identity.protocols import IMailSender
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.mail import MailTemplate, RenderedMail, compose, resolve_lang

_log = logging.getLogger(__name__)

_TEMPLATES: dict[NotificationKind, MailTemplate] = {
    NotificationKind.project_invitation: MailTemplate.project_invitation,
    NotificationKind.access_request: MailTemplate.access_request,
    NotificationKind.transfer_request: MailTemplate.transfer_request,
}


class SmtpNotificationMailer:
    def __init__(self, sender: IMailSender, public_url: str | None) -> None:
        self._sender = sender
        self._public_url = public_url

    @property
    def enabled(self) -> bool:
        return self._sender.enabled

    def render_notification(
        self, to_email: str, kind: NotificationKind, payload: NotificationPayload, *, locale: str | None
    ) -> RenderedMail | None:
        """Письмо уведомления; None для видов, о которых письмо не шлют."""
        template = _TEMPLATES.get(kind)
        if template is None:
            return None
        return compose(
            template,
            resolve_lang(locale),
            to=to_email,
            server_url=self._public_url,
            values={"actor": payload.actor_name, "project": payload.project_name, "role": payload.role},
        )

    async def send_notification(
        self, to_email: str, kind: NotificationKind, payload: NotificationPayload, *, locale: str | None
    ) -> bool:
        rendered = self.render_notification(to_email, kind, payload, locale=locale)
        if rendered is None or not self._sender.enabled:
            return False
        return await self._send(to_email, rendered, kind=kind.value)

    async def send_invitation(
        self,
        to_email: str,
        *,
        project_name: str,
        inviter_name: str,
        role: str,
        link: str,
        message: str | None,
        locale: str | None,
        expires_at: datetime | None = None,
    ) -> bool:
        if not self._sender.enabled:
            return False
        rendered = compose(
            MailTemplate.project_invitation_link,
            resolve_lang(locale),
            to=to_email,
            server_url=self._public_url,
            link=link,
            expires_at=expires_at,
            values={"actor": inviter_name, "project": project_name, "role": role},
            note=message,
        )
        return await self._send(to_email, rendered, kind="project_invitation_link")

    async def _send(self, to_email: str, mail: RenderedMail, *, kind: str) -> bool:
        try:
            await self._sender.send(to_email, mail.subject, mail.text, html=mail.html)
        except Exception:
            _log.warning("notification mail failed", extra={"kind": kind})
            return False
        return True
