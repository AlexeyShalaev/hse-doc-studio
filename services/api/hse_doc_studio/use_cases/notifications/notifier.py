"""`INotifier`: запись во «Входящие» и письмо для видов S15.

Каждое письмо, положенное по виду, оставляет строку журнала писем (docs/design/mail-log.md, P8..P13): ушло, не
ушло, не отправлялось без SMTP (`not_sent`) или не положено получателю (`suppressed`: почта не подтверждена, вход
закрыт).
"""

from __future__ import annotations

import asyncio
import logging

from hse_doc_studio.core.background import current_background_task
from hse_doc_studio.core.identity.entities import User, UserStatus
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import MAILED_KINDS, NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotificationMailer, INotificationRepository
from hse_doc_studio.core.mail.journal import MailOrigin, MailSkipReason

_log = logging.getLogger(__name__)


def _skip_reason(user: User) -> MailSkipReason | None:
    """Почему письмо не положено получателю: вход закрыт (отключён, ждёт одобрения) или почта не подтверждена
    (в том числе регистрация, которая ждёт подтверждения). Это решение продукта, оно важнее настроек SMTP: с почтой
    письмо всё равно не ушло бы, поэтому без SMTP такой получатель тоже `suppressed`, а не `not_sent`."""
    if not user.can_sign_in and user.status is not UserStatus.pending_verification:
        return MailSkipReason.account_blocked
    if not user.email_verified or not user.can_sign_in:
        return MailSkipReason.email_unverified
    return None


def _origin(kind: NotificationKind) -> MailOrigin:
    """Напоминание из фоновой задачи это автонапоминание маршрута (`SigningReminderSweeper`), остальное
    уведомление: кто его вызвал, журнал берёт из контекста."""
    if kind is NotificationKind.signing_reminder and current_background_task() is not None:
        return MailOrigin.signing_auto_reminder
    return MailOrigin.notification


class Notifier:
    """Уведомление пишется в той же транзакции, что и событие; письмо уходит отдельной задачей и действию
    не мешает (сбой SMTP только в журнале писем). Письмо получает только подтверждённая почта открытого аккаунта."""

    def __init__(
        self,
        notifications: INotificationRepository,
        users: IUserRepository,
        mailer: INotificationMailer,
        *,
        background: bool = True,
        clock: Clock = utc_now,
    ) -> None:
        self._notifications = notifications
        self._users = users
        self._mailer = mailer
        self._background = background
        self._clock = clock
        self._pending: set[asyncio.Task[None]] = set()

    async def notify(
        self,
        user_id: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        dedupe_key: str | None = None,
        mail: bool = True,
    ) -> None:
        await self._notifications.add(user_id, kind, payload, dedupe_key=dedupe_key, now=self._clock())
        if not mail or kind not in MAILED_KINDS:
            return
        # Без SMTP задача всё равно идёт: строка журнала `not_sent` нужна и тогда (L2).
        origin = _origin(kind)
        if self._background:
            task = asyncio.create_task(self._mail(user_id, kind, payload, origin))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
        else:
            await self._mail(user_id, kind, payload, origin)

    async def drain(self) -> None:
        """Дожидается писем, начатых в фоне (тесты и остановка)."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    async def _mail(
        self, user_id: str, kind: NotificationKind, payload: NotificationPayload, origin: MailOrigin
    ) -> None:
        try:
            user = await self._users.get(user_id)
            if user is None:
                # Человека уже нет: адреса нет, писать в журнал некому.
                return
            reason = _skip_reason(user)
            if reason is not None:
                await self._mailer.skip_notification(
                    user.email, kind, payload, locale=user.locale, reason=reason, to_user_id=user.id, origin=origin
                )
                return
            # Без SMTP диспетчер сам пишет `not_sent`.
            await self._mailer.send_notification(
                user.email, kind, payload, locale=user.locale, to_user_id=user.id, origin=origin
            )
        except Exception:
            _log.warning("notification mail skipped", extra={"kind": kind.value})
