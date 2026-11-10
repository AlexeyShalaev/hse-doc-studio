"""Письма уведомлений: приглашение в проект, запрос доступа, передача владения, маршрут подписания (ru и en).

В письме только подписи из уведомления и ссылка на «Входящие», страницу приглашения, страницу подписи или точку
сдачи: секретов там нет, кроме токена ссылки приглашения, который адресат и должен получить. Ссылки маршрута
подписания без токенов: страница открывается только после входа (docs/design/signing-route.md, 6.6). Сбой SMTP
действию не мешает. Тексты и вёрстка лежат в `core.mail`.
"""

from __future__ import annotations

import logging
from datetime import datetime
from urllib.parse import quote

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.identity.protocols import IMailSender
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.mail import MailTemplate, RenderedMail, compose, resolve_lang
from hse_doc_studio.core.mail.compose import format_moment, server_origin

_log = logging.getLogger(__name__)

_TEMPLATES: dict[NotificationKind, MailTemplate] = {
    NotificationKind.project_invitation: MailTemplate.project_invitation,
    NotificationKind.access_request: MailTemplate.access_request,
    NotificationKind.transfer_request: MailTemplate.transfer_request,
    NotificationKind.signing_request: MailTemplate.signing_request,
    NotificationKind.signing_reminder: MailTemplate.signing_reminder,
    NotificationKind.signing_returned: MailTemplate.signing_returned,
    NotificationKind.signing_completed: MailTemplate.signing_completed,
}
# Подписанту письмо ведёт на страницу подписи, автору на точку сдачи.
_TO_SIGNING_PAGE = frozenset({NotificationKind.signing_request, NotificationKind.signing_reminder})
_TO_CHECKPOINT = frozenset({NotificationKind.signing_returned, NotificationKind.signing_completed})


def _template(kind: NotificationKind, payload: NotificationPayload) -> MailTemplate | None:
    if kind is NotificationKind.signing_request and payload.outcome == "sign":
        return MailTemplate.signing_request_sign
    if kind is NotificationKind.signing_request and payload.new_version:
        return MailTemplate.signing_request_new_version
    return _TEMPLATES.get(kind)


def _segment(value: str | None) -> str:
    return quote(value or "", safe="")


def _signing_link(kind: NotificationKind, payload: NotificationPayload, public_url: str | None) -> str | None:
    """Адрес страницы подписи или точки сдачи на публичном адресе установки; без адреса письмо без кнопки."""
    origin = server_origin(public_url)
    if origin is None or not payload.project_id:
        return None
    project = _segment(payload.project_id)
    if kind in _TO_SIGNING_PAGE and payload.ref_id:
        return f"{origin}/sign/{project}/{_segment(payload.ref_id)}"
    if kind in _TO_CHECKPOINT and payload.profile_id:
        return f"{origin}/projects/{project}/submit/cp/{_segment(payload.profile_id)}"
    return None


def _deadline(payload: NotificationPayload, lang: Lang) -> str | None:
    if not payload.deadline:
        return None
    try:
        return format_moment(lang, datetime.fromisoformat(payload.deadline))
    except ValueError:
        return None


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
        template = _template(kind, payload)
        if template is None:
            return None
        lang = resolve_lang(locale)
        if kind in _TO_SIGNING_PAGE or kind in _TO_CHECKPOINT:
            returned = kind is NotificationKind.signing_returned
            new_version = template is MailTemplate.signing_request_new_version
            return compose(
                template,
                lang,
                to=to_email,
                server_url=self._public_url,
                link=_signing_link(kind, payload, self._public_url),
                values={
                    "actor": payload.actor_name,
                    "project": payload.project_name,
                    # Название точки в `excerpt`; у возврата там комментарий, он идёт отдельным блоком.
                    "profile": None if returned else (payload.excerpt or payload.profile_id or ""),
                    "deadline": _deadline(payload, lang),
                    # Новая версия (12.6): изменившиеся документы получателя.
                    "changed": payload.changed_names if new_version else None,
                },
                # У возврата комментарий, у новой версии сообщение автора («Что изменилось» его заменяет).
                note=payload.excerpt if returned else payload.message if new_version else None,
            )
        return compose(
            template,
            lang,
            to=to_email,
            server_url=self._public_url,
            values={"actor": payload.actor_name, "project": payload.project_name, "role": payload.role},
            # Сообщение приглашающего; экранирование и предел длины на стороне `core.mail`.
            note=payload.excerpt if kind is NotificationKind.project_invitation else None,
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
