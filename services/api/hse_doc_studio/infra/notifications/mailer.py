"""Письма трека invites: приглашение в проект, запрос доступа, передача владения (ru и en).

В письме только подписи из уведомления и ссылка на «Входящие» или на страницу приглашения: секретов там нет,
кроме токена ссылки приглашения, который адресат и должен получить. Сбой SMTP действию не мешает.
"""

from __future__ import annotations

import logging

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import current_interface_language
from hse_doc_studio.core.identity.protocols import IMailSender
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload

_log = logging.getLogger(__name__)

_ROLE_WORDS: dict[str, tuple[str, str]] = {
    "reader": ("Читатель", "Reader"),
    "reviewer": ("Рецензент", "Reviewer"),
    "editor": ("Редактор", "Editor"),
    "owner": ("Владелец", "Owner"),
}

# (тема, текст) для ru и en; подстановки: actor, project, role, link.
_TEXTS: dict[NotificationKind, tuple[tuple[str, str], tuple[str, str]]] = {
    NotificationKind.project_invitation: (
        (
            "{actor} приглашает вас в «{project}»",
            (
                "{actor} приглашает вас в проект «{project}» с ролью «{role}».\n"
                "Принять или отклонить приглашение можно во «Входящих»:\n{link}"
            ),
        ),
        (
            "{actor} invites you to “{project}”",
            (
                "{actor} invites you to the project “{project}” as {role}.\n"
                "Accept or decline the invitation in your Inbox:\n{link}"
            ),
        ),
    ),
    NotificationKind.access_request: (
        (
            "{actor} просит доступ к «{project}»",
            "{actor} просит доступ к проекту «{project}».\nОдобрить или отклонить запрос можно во «Входящих»:\n{link}",
        ),
        (
            "{actor} requests access to “{project}”",
            "{actor} requests access to the project “{project}”.\nApprove or deny the request in your Inbox:\n{link}",
        ),
    ),
    NotificationKind.transfer_request: (
        (
            "{actor} передаёт вам проект «{project}»",
            (
                "{actor} передаёт вам проект «{project}». После принятия вы станете его владельцем.\n"
                "Принять или отклонить передачу можно во «Входящих»:\n{link}"
            ),
        ),
        (
            "{actor} is transferring “{project}” to you",
            (
                "{actor} is transferring the project “{project}” to you. Once you accept, you become its owner.\n"
                "Accept or decline the transfer in your Inbox:\n{link}"
            ),
        ),
    ),
}

_INVITATION = (
    (
        "{actor} приглашает вас в «{project}»",
        (
            "{actor} приглашает вас в проект «{project}» в Студии с ролью «{role}».{message}\n\n"
            "Чтобы принять приглашение, откройте ссылку и войдите или зарегистрируйтесь с этим адресом:\n{link}\n\n"
            "Если вы не ждали приглашения, просто проигнорируйте письмо."
        ),
    ),
    (
        "{actor} invites you to “{project}”",
        (
            "{actor} invites you to the project “{project}” in the Studio as {role}.{message}\n\n"
            "To accept, open the link and sign in or sign up with this address:\n{link}\n\n"
            "If you did not expect this invitation, just ignore this message."
        ),
    ),
)

INBOX_PATH = "/inbox"


def _lang(locale: str | None) -> Lang:
    return Lang(locale) if locale in ("ru", "en") else current_interface_language()


def role_word(role: str | None, lang: Lang) -> str:
    words = _ROLE_WORDS.get(role or "")
    if words is None:
        return role or ""
    return words[1] if lang is Lang.en else words[0]


def render_notification(
    kind: NotificationKind, payload: NotificationPayload, lang: Lang, public_url: str | None
) -> tuple[str, str] | None:
    """Тема и текст письма; None для видов, о которых письмо не шлют."""
    texts = _TEXTS.get(kind)
    if texts is None:
        return None
    subject, body = texts[1] if lang is Lang.en else texts[0]
    values = {
        "actor": payload.actor_name or "",
        "project": payload.project_name or "",
        "role": role_word(payload.role, lang),
        "link": f"{(public_url or '').rstrip('/')}{INBOX_PATH}",
    }
    return subject.format(**values), body.format(**values)


def render_invitation(
    *, project_name: str, inviter_name: str, role: str, link: str, message: str | None, lang: Lang
) -> tuple[str, str]:
    subject, body = _INVITATION[1] if lang is Lang.en else _INVITATION[0]
    note = f"\n\n«{message}»" if message else ""
    values = {"actor": inviter_name, "project": project_name, "role": role_word(role, lang), "link": link}
    return subject.format(**values), body.format(**values, message=note)


class SmtpNotificationMailer:
    def __init__(self, sender: IMailSender, public_url: str | None) -> None:
        self._sender = sender
        self._public_url = public_url

    @property
    def enabled(self) -> bool:
        return self._sender.enabled

    async def send_notification(
        self, to_email: str, kind: NotificationKind, payload: NotificationPayload, *, locale: str | None
    ) -> bool:
        rendered = render_notification(kind, payload, _lang(locale), self._public_url)
        if rendered is None or not self._sender.enabled:
            return False
        return await self._send(to_email, *rendered, kind=kind.value)

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
    ) -> bool:
        if not self._sender.enabled:
            return False
        subject, body = render_invitation(
            project_name=project_name,
            inviter_name=inviter_name,
            role=role,
            link=link,
            message=message,
            lang=_lang(locale),
        )
        return await self._send(to_email, subject, body, kind="project_invitation_link")

    async def _send(self, to_email: str, subject: str, body: str, *, kind: str) -> bool:
        try:
            await self._sender.send(to_email, subject, body)
        except Exception:
            _log.warning("notification mail failed", extra={"kind": kind})
            return False
        return True
