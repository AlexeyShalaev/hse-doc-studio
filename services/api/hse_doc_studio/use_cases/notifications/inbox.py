"""«Входящие»: страница уведомлений, отметка прочитанного, сводка счётчиков и уборка старых уведомлений."""

from __future__ import annotations

from collections.abc import Sequence

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import NOTIFICATION_RETENTION, InboxSummary, Notification
from hse_doc_studio.core.invitations.protocols import (
    IAccessRequestRepository,
    INotificationRepository,
    IProjectInvitationRepository,
    IProjectTransferRepository,
)
from hse_doc_studio.core.listing import Found, Window, clamp_limit
from hse_doc_studio.use_cases.orgs.access import user_id_of


class ListNotificationsUC:
    def __init__(self, notifications: INotificationRepository) -> None:
        self._notifications = notifications

    async def execute(self, actor: Actor, *, unread_only: bool, window: Window) -> Found[Notification]:
        window = Window(clamp_limit(window.limit), max(0, window.offset))
        return await self._notifications.page(user_id_of(actor), unread_only=unread_only, window=window)


class MarkNotificationsReadUC:
    def __init__(self, notifications: INotificationRepository, clock: Clock = utc_now) -> None:
        self._notifications = notifications
        self._clock = clock

    async def execute(self, actor: Actor, ids: Sequence[str] | None) -> int:
        return await self._notifications.mark_read(user_id_of(actor), ids, self._clock())


class InboxSummaryUC:
    def __init__(
        self,
        notifications: INotificationRepository,
        invitations: IProjectInvitationRepository,
        transfers: IProjectTransferRepository,
        requests: IAccessRequestRepository,
        clock: Clock = utc_now,
    ) -> None:
        self._notifications = notifications
        self._invitations = invitations
        self._transfers = transfers
        self._requests = requests
        self._clock = clock

    async def execute(self, actor: Actor) -> InboxSummary:
        user_id = user_id_of(actor)
        now = self._clock()
        return InboxSummary(
            unread=await self._notifications.unread_count(user_id),
            invitations=await self._invitations.count_pending_for_user(user_id, now),
            transfers=await self._transfers.count_pending_for_user(user_id, now),
            access_requests=await self._requests.count_pending_managed(user_id),
        )

    async def badge(self, user_id: str) -> int:
        """Число на колокольчике: непрочитанные уведомления плюс ожидающие приглашения и передачи."""
        now = self._clock()
        return (
            await self._notifications.unread_count(user_id)
            + await self._invitations.count_pending_for_user(user_id, now)
            + await self._transfers.count_pending_for_user(user_id, now)
        )


class PurgeNotificationsUC:
    def __init__(self, notifications: INotificationRepository, clock: Clock = utc_now) -> None:
        self._notifications = notifications
        self._clock = clock

    async def execute(self) -> int:
        return await self._notifications.purge(self._clock() - NOTIFICATION_RETENTION)
