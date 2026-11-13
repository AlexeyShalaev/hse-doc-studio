"""Напоминание автору о сроке контрольной точки: периодическая задача лидера `checkpoint_reminders`.

docs/design/signing-route.md, 16.7. За `reminder_days` суток до срока точки (3 по умолчанию), если пакет точки к сроку
ещё не собран, владелец проекта и участники с персоной автора получают уведомление `checkpoint_due` во «Входящие» и
письмом. Руководителям не напоминает: их срок это срок маршрута, о нём напоминает маршрут (5.7). После срока
напоминаний нет: «просрочено» видно на точке и в списке.

Одно напоминание на срок: ключ повтора `checkpoint:<проект>:<точка>:<срок>:due` (`reminder_key`). Уведомление
каждому человеку пишется своей транзакцией под блокировкой этого ключа и только если уведомления с ключом у него ещё
нет, поэтому повторный проход, перезапуск и смена лидера второй раз ничего не отправляют, а новый срок даёт новое
напоминание.
Сбой одной точки (битая запись, недоступный проект) остальным не мешает.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from hse_doc_studio.core.checkpoint_deadlines import (
    PACKAGE_WINDOW,
    REMINDER_DAYS,
    packaged_at,
    reminder_due,
    reminder_key,
)
from hse_doc_studio.core.checkpoint_reminders import DueCheckpoint, ICheckpointReminderStore, ReminderRecipient
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.invitations.protocols import INotifier
from hse_doc_studio.core.signatures.dates import DISPLAY_ZONE
from hse_doc_studio.core.uow import IUnitOfWork

_log = logging.getLogger(__name__)


class CheckpointReminderSweeper:
    def __init__(  # noqa: PLR0913 — порты перечислены явно
        self,
        store: ICheckpointReminderStore,
        notifier: INotifier,
        uow: IUnitOfWork,
        *,
        days: int = REMINDER_DAYS,
        clock: Clock = utc_now,
    ) -> None:
        self._store = store
        self._notifier = notifier
        self._uow = uow
        self._days = days
        self._clock = clock

    async def run(self) -> int:
        """Отправить напоминания, которым пришло время; возвращает число уведомлений."""
        if self._days <= 0:
            return 0
        now = self._clock()
        sent = 0
        for point in await self._store.due(now=now, until=now + timedelta(days=self._days)):
            try:
                sent += await self._remind(point)
            except Exception:
                _log.warning(
                    "checkpoint reminder skipped",
                    extra={"project_id": str(point.project_id), "profile_id": point.profile_id},
                    exc_info=True,
                )
        return sent

    async def _remind(self, point: DueCheckpoint) -> int:
        async with self._uow.begin():
            now = self._clock()
            built = await self._store.built(point.project_id, point.profile_id, since=point.deadline - PACKAGE_WINDOW)
            if not reminder_due(point.deadline, now=now, packaged=packaged_at(point.deadline, built), days=self._days):
                return 0
            people = await self._store.recipients(point.project_id)
        key = reminder_key(point.project_id, point.profile_id, point.deadline)
        sent = 0
        for person in people:
            sent += await self._notify(point, person, key)
        return sent

    async def _notify(self, point: DueCheckpoint, person: ReminderRecipient, key: str) -> int:
        """Одному человеку своей транзакцией под блокировкой ключа: уведомление последнее в ней, поэтому письмо
        (оно уходит задачей) идёт уже после записи и не делит с ней соединение."""
        async with self._uow.begin():
            await self._store.lock(key)
            if await self._store.reminded([person.user_id], key):
                return 0
            payload = NotificationPayload(
                project_id=str(point.project_id),
                project_name=point.project_name or None,
                excerpt=point.label(person.locale),
                profile_id=point.profile_id,
                deadline=point.deadline.astimezone(DISPLAY_ZONE).isoformat(),
            )
            await self._notifier.notify(person.user_id, NotificationKind.checkpoint_due, payload, dedupe_key=key)
        return 1
