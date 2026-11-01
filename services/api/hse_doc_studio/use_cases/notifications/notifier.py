"""`INotifier`: запись во «Входящие» и письмо для видов S15, если настроен SMTP."""

from __future__ import annotations

import asyncio
import logging

from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import MAILED_KINDS, NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotificationMailer, INotificationRepository

_log = logging.getLogger(__name__)


class Notifier:
    """Уведомление пишется в той же транзакции, что и событие; письмо уходит отдельной задачей и действию
    не мешает (сбой SMTP только в журнале). Письмо получает только подтверждённая почта."""

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
    ) -> None:
        await self._notifications.add(user_id, kind, payload, dedupe_key=dedupe_key, now=self._clock())
        if kind not in MAILED_KINDS or not self._mailer.enabled:
            return
        if self._background:
            task = asyncio.create_task(self._mail(user_id, kind, payload))
            self._pending.add(task)
            task.add_done_callback(self._pending.discard)
        else:
            await self._mail(user_id, kind, payload)

    async def drain(self) -> None:
        """Дожидается писем, начатых в фоне (тесты и остановка)."""
        if self._pending:
            await asyncio.gather(*self._pending, return_exceptions=True)

    async def _mail(self, user_id: str, kind: NotificationKind, payload: NotificationPayload) -> None:
        try:
            user = await self._users.get(user_id)
            if user is None or not user.email_verified or not user.can_sign_in:
                return
            await self._mailer.send_notification(user.email, kind, payload, locale=user.locale)
        except Exception:
            _log.warning("notification mail skipped", extra={"kind": kind.value})
