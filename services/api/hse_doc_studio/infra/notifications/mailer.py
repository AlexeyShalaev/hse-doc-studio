"""Письма уведомлений: приглашение в проект, запрос доступа, передача владения, маршрут подписания (ru и en).

В письме только подписи из уведомления и ссылка на «Входящие», страницу приглашения, страницу подписи или точку
сдачи: секретов там нет, кроме токена ссылки приглашения, который адресат и должен получить. Ссылки маршрута
подписания без токенов: страница открывается только после входа (docs/design/signing-route.md, 6.6). Тексты и
вёрстка лежат в `core.mail`.

Письмо уходит через `MailDispatcher` (docs/design/mail-log.md, L1, пути P8..P14): он отправляет, разбирает сбой и
пишет строку журнала. Сбой SMTP действию не мешает: диспетчер не бросает, итог виден в журнале писем.
"""

from __future__ import annotations

from datetime import datetime
from urllib.parse import quote

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.mail import MailTemplate, RenderedMail, resolve_lang
from hse_doc_studio.core.mail.compose import fixed_path, format_moment, server_origin
from hse_doc_studio.core.mail.journal import MailLinkKind, MailOrigin, MailRefKind, MailRequest, MailSkipReason
from hse_doc_studio.use_cases.mail.dispatch import MailDispatcher

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
# Объект письма в журнале (L9): `ref_id` уведомления это id приглашения, запроса, передачи или маршрута.
_REF_KINDS: dict[NotificationKind, MailRefKind] = {
    NotificationKind.project_invitation: MailRefKind.project_invitation,
    NotificationKind.access_request: MailRefKind.access_request,
    NotificationKind.transfer_request: MailRefKind.transfer,
    **dict.fromkeys(_TO_SIGNING_PAGE | _TO_CHECKPOINT, MailRefKind.signing_route),
}


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


def _ref(kind: NotificationKind, payload: NotificationPayload) -> tuple[MailRefKind | None, str | None]:
    ref_kind = _REF_KINDS.get(kind)
    if ref_kind is None or not payload.ref_id:
        return None, None
    return ref_kind, payload.ref_id


class SmtpNotificationMailer:
    def __init__(self, dispatcher: MailDispatcher, public_url: str | None) -> None:
        self._dispatcher = dispatcher
        self._public_url = public_url

    @property
    def enabled(self) -> bool:
        return self._dispatcher.enabled

    def notification_request(  # noqa: PLR0913 — поля одного письма
        self,
        to_email: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        locale: str | None,
        to_user_id: str | None = None,
        origin: MailOrigin = MailOrigin.notification,
    ) -> MailRequest | None:
        """Письмо уведомления для диспетчера; None для видов, о которых письмо не шлют."""
        template = _template(kind, payload)
        if template is None:
            return None
        lang = resolve_lang(locale)
        ref_kind, ref_id = _ref(kind, payload)
        link, values, note = self._content(kind, template, payload, lang)
        return MailRequest(
            template=template,
            lang=lang,
            to=to_email,
            server_url=self._public_url,
            origin=origin,
            # Ссылка без токена: страница подписи или точка сдачи, у остальных видов постоянная страница вида
            # («Входящие»); без публичного адреса у маршрута кнопки нет.
            link_kind=MailLinkKind.page if link or fixed_path(template) else MailLinkKind.none,
            link=link,
            values=values,
            note=note,
            to_user_id=to_user_id,
            project_id=payload.project_id,
            ref_kind=ref_kind,
            ref_id=ref_id,
        )

    def _content(
        self, kind: NotificationKind, template: MailTemplate, payload: NotificationPayload, lang: Lang
    ) -> tuple[str | None, dict[str, str | None], str | None]:
        """Ссылка, значения шаблона и сообщение человека."""
        if kind in _TO_SIGNING_PAGE or kind in _TO_CHECKPOINT:
            returned = kind is NotificationKind.signing_returned
            new_version = template is MailTemplate.signing_request_new_version
            values = {
                "actor": payload.actor_name,
                "project": payload.project_name,
                # Название точки в `excerpt`; у возврата там комментарий, он идёт отдельным блоком.
                "profile": None if returned else (payload.excerpt or payload.profile_id or ""),
                "deadline": _deadline(payload, lang),
                # Новая версия (12.6): изменившиеся документы получателя.
                "changed": payload.changed_names if new_version else None,
            }
            # У возврата комментарий, у новой версии сообщение автора («Что изменилось» его заменяет).
            note = payload.excerpt if returned else payload.message if new_version else None
            return _signing_link(kind, payload, self._public_url), values, note
        values = {"actor": payload.actor_name, "project": payload.project_name, "role": payload.role}
        # Сообщение приглашающего; экранирование и предел длины на стороне `core.mail`.
        return None, values, payload.excerpt if kind is NotificationKind.project_invitation else None

    def render_notification(
        self, to_email: str, kind: NotificationKind, payload: NotificationPayload, *, locale: str | None
    ) -> RenderedMail | None:
        """Письмо уведомления как уйдёт; None для видов, о которых письмо не шлют."""
        request = self.notification_request(to_email, kind, payload, locale=locale)
        return request.render() if request is not None else None

    async def send_notification(  # noqa: PLR0913 — поля одного письма
        self,
        to_email: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        locale: str | None,
        to_user_id: str | None = None,
        origin: MailOrigin = MailOrigin.notification,
    ) -> bool:
        request = self.notification_request(
            to_email, kind, payload, locale=locale, to_user_id=to_user_id, origin=origin
        )
        if request is None:
            return False
        return (await self._dispatcher.send(request)).sent

    async def skip_notification(  # noqa: PLR0913 — поля одного письма
        self,
        to_email: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        locale: str | None,
        reason: MailSkipReason,
        to_user_id: str | None = None,
        origin: MailOrigin = MailOrigin.notification,
    ) -> None:
        request = self.notification_request(
            to_email, kind, payload, locale=locale, to_user_id=to_user_id, origin=origin
        )
        if request is not None:
            await self._dispatcher.skip(request, reason)

    async def send_invitation(  # noqa: PLR0913 — поля одного письма
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
        origin: MailOrigin = MailOrigin.project_invite,
        to_user_id: str | None = None,
        project_id: str | None = None,
        invitation_id: str | None = None,
    ) -> bool:
        request = MailRequest(
            template=MailTemplate.project_invitation_link,
            lang=resolve_lang(locale),
            to=to_email,
            server_url=self._public_url,
            origin=origin,
            link_kind=MailLinkKind.token,
            link=link,
            expires_at=expires_at,
            values={"actor": inviter_name, "project": project_name, "role": role},
            note=message,
            to_user_id=to_user_id,
            project_id=project_id,
            ref_kind=MailRefKind.project_invitation if invitation_id else None,
            ref_id=invitation_id,
        )
        return (await self._dispatcher.send(request)).sent
