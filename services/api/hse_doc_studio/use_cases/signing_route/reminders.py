"""Напоминания подписантам: «Напомнить» у автора и автонапоминания сервера (docs/design/signing-route.md, 5.7).

Оба пути под блокировкой строки маршрута считают расчёт на текущих фактах, отмечают напоминание у участника
(`reminded_at`, `reminders`), пишут событие в историю маршрута и уведомление `signing_reminder` одной транзакцией.
Напоминают только тому, чья очередь по расчёту; если документ изменился и маршрут по расчёту уже не идёт,
напоминать не о чем.

Приглашённому, который ещё не принял приглашение, «Напомнить» повторяет приглашение (раздел 6.5): секрет ссылки
меняется в той же транзакции, письмо уходит после неё; без SMTP ссылка с `?next=/sign/...` возвращается автору.
Автонапоминания приглашённых не трогают: писать некуда, а повтор приглашения ломает прежнюю ссылку.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.invitations.protocols import INotificationMailer
from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.engine import evaluate, request_outcome
from hse_doc_studio.core.signing_route.entities import (
    TURN_STATES,
    EventKind,
    Notice,
    Participant,
    ParticipantState,
    RequestOutcome,
    RouteEvent,
    RouteStatus,
    SigningRoute,
)
from hse_doc_studio.core.signing_route.ports import IRouteFacts, ISigningNotifier
from hse_doc_studio.core.signing_route.reminders import (
    REMINDABLE_STATES,
    ReminderPolicy,
    ReminderTrigger,
    auto_reminders,
    due_reminder,
    mark_reminded,
    may_be_due,
    not_waiting,
    remind_available_at,
    reminder_event,
)
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.projects.invitations import RenewedInvitation, ResendInvitationUC
from hse_doc_studio.use_cases.signing_route.scenario import RouteScenario, RouteServices, actor_uuid

_log = logging.getLogger(__name__)

ReminderDelivery = Literal["inbox", "email", "manual"]


@dataclass(frozen=True)
class Reminder:
    """Ответ «Напомнить»: как доставлено; `link` ссылка приглашения, когда её пересылает сам автор (`manual`)."""

    participant_id: UUID
    delivery: ReminderDelivery
    link: str | None = None


def signing_page_path(project_id: UUID, route_id: UUID) -> str:
    """Страница подписанта: туда ведёт приглашение после принятия (`?next=`)."""
    return f"/sign/{project_id}/{route_id}"


def _participant_not_found() -> NotFoundError:
    return NotFoundError(localized_error("Участник маршрута не найден", "Route participant not found"))


def _check_interval(participant: Participant, at: datetime) -> None:
    available = remind_available_at(participant)
    if available is None or available <= at:
        return
    seconds = max(1, math.ceil((available - at).total_seconds()))
    raise IdentityError(
        IdentityErrorCode.rate_limited,
        retry_after_s=seconds,
        extra={"retry_after": seconds, "available_at": available.isoformat()},
    )


class SigningRouteReminding(RouteScenario):
    """«Напомнить» у того, кто управляет маршрутом: участнику, чья очередь, или приглашённому."""

    def __init__(
        self,
        services: RouteServices,
        invitations: ResendInvitationUC,
        users: IUserRepository,
        mailer: INotificationMailer,
    ) -> None:
        super().__init__(services)
        self._invitations = invitations
        self._users = users
        self._mailer = mailer

    async def remind(self, actor: Actor, project_id: UUID, route_id: UUID, participant_id: UUID) -> Reminder:
        actor_id = actor_uuid(actor)
        at = self._s.clock()
        renewed: RenewedInvitation | None = None
        delivery: ReminderDelivery = "inbox"
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            p = next((x for x in route.participants if x.id == participant_id), None)
            if p is None:
                raise _participant_not_found()
            outcome = await self._turn(route, p)
            _check_interval(p, at)
            if outcome is None:
                renewed = await self._reinvite(actor, route, p, at)
            else:
                delivery = await self._delivery(p)
                event = reminder_event(route, p.id, ReminderTrigger.manual, at=at, actor_id=actor_id, delivery=delivery)
                saved = await self._s.routes.save(mark_reminded(route, p.id, at=at), events=[event])
                await self.notify(saved, [Notify(Notice.reminder, (p.id,), outcome=outcome)], actor_id=actor_id)
        if renewed is None:
            return Reminder(p.id, delivery)
        sent = await self._invitations.deliver(actor, renewed, next_path=signing_page_path(project_id, route_id))
        return Reminder(p.id, sent.delivery, sent.link)

    async def _turn(self, route: SigningRoute, p: Participant) -> RequestOutcome | None:
        """О чём напомнить участнику по расчёту; None у приглашённого. Не его очередь: `participant_not_waiting`."""
        if route.status is not RouteStatus.active:
            raise not_waiting()
        point = await self._s.points.load(route.project_id, route.profile_id)
        loaded = await self._s.facts.load(point, route)
        evaluation = evaluate(route, loaded.facts)
        view = evaluation.participant(p.id)
        if evaluation.status is not RouteStatus.active or view.state not in REMINDABLE_STATES:
            raise not_waiting()
        if view.state is ParticipantState.invited:
            return None
        outcome = request_outcome(view.next_action)
        if outcome is None:
            raise not_waiting()
        return outcome

    async def _reinvite(self, actor: Actor, route: SigningRoute, p: Participant, at: datetime) -> RenewedInvitation:
        """Повторить приглашение участника и записать это в маршрут; письмо уходит после транзакции."""
        if p.invitation_id is None:
            # Человека на этот шаг ещё не пригласили: напоминать некому.
            raise not_waiting()
        renewed = await self._invitations.renew(actor, route.project_id, p.invitation_id)
        event = RouteEvent(
            route.id,
            route.round,
            at,
            EventKind.invited,
            actor_uuid(actor),
            p.id,
            {"invitation_id": p.invitation_id, "trigger": ReminderTrigger.manual.value},
        )
        await self._s.routes.save(mark_reminded(route, p.id, at=at), events=[event])
        return renewed

    async def _delivery(self, p: Participant) -> ReminderDelivery:
        """Письмо получает только подтверждённая почта при настроенном SMTP, как у любого уведомления."""
        if p.user_id is None or not self._mailer.enabled:
            return "inbox"
        user = await self._users.get(p.user_id.hex)
        return "email" if user is not None and user.email_verified and user.can_sign_in else "inbox"


@dataclass(frozen=True)
class _Due:
    participant_id: UUID
    trigger: ReminderTrigger
    outcome: RequestOutcome


class SigningReminderSweeper:
    """Автонапоминания: периодическая задача лидера (`signing_reminders`).

    Проход обходит идущие маршруты. Что пора напомнить, решают правила `core.signing_route.reminders` по
    записанному в маршруте и его истории, а отметка, событие и уведомление пишутся одной транзакцией под
    блокировкой строки маршрута. Поэтому повторный проход, перезапуск сервера и смена лидера ничего не
    отправляют второй раз. Сбой одного маршрута (битый проект, снятый пак) остальным не мешает.
    """

    def __init__(  # noqa: PLR0913 — порты перечислены явно
        self,
        routes: ISigningRouteRepository,
        facts: IRouteFacts,
        notifier: ISigningNotifier,
        uow: IUnitOfWork,
        policy: ReminderPolicy | None = None,
        clock: Clock = utc_now,
    ) -> None:
        self._routes = routes
        self._facts = facts
        self._notifier = notifier
        self._uow = uow
        self._policy = policy or ReminderPolicy()
        self._clock = clock

    async def run(self) -> int:
        """Отправить автонапоминания, которым пришло время; возвращает их число."""
        if self._policy.max_auto <= 0:
            return 0
        now = self._clock()
        sent = 0
        for route in await self._routes.list_watching():
            if route.status is not RouteStatus.active or not may_be_due(route, self._policy, now=now):
                continue
            try:
                sent += await self._remind(route.project_id, route.id, now)
            except Exception:
                _log.warning("signing reminders skipped", extra={"route_id": str(route.id)}, exc_info=True)
        return sent

    async def _remind(self, project_id: UUID, route_id: UUID, now: datetime) -> int:
        async with self._uow.begin():
            route = await self._routes.get(project_id, route_id, lock=True)
            if route is None or route.status is not RouteStatus.active:
                return 0
            due = await self._due(route, now)
            if not due:
                return 0
            events: list[RouteEvent] = []
            for item in due:
                route = mark_reminded(route, item.participant_id, at=now)
                events.append(reminder_event(route, item.participant_id, item.trigger, at=now))
            saved = await self._routes.save(route, events=events)
            notices = [Notify(Notice.reminder, (item.participant_id,), outcome=item.outcome) for item in due]
            await self._notifier.notify(saved, notices, actor_id=None)
        return len(due)

    async def _due(self, route: SigningRoute, now: datetime) -> list[_Due]:
        """Кому пора напомнить: его очередь по расчёту на текущих фактах и подошло время по правилам."""
        facts = await self._facts.facts(route)
        if facts is None:
            return []
        evaluation = evaluate(route, facts)
        if evaluation.status is not RouteStatus.active:
            # Документ изменился: маршрут остановит сверка, просить подписать эту версию уже нельзя.
            return []
        sent = auto_reminders(route, await self._routes.list_events(route.id, round=route.round))
        due: list[_Due] = []
        for p in route.participants:
            view = evaluation.participant(p.id)
            outcome = request_outcome(view.next_action)
            if view.state not in TURN_STATES or outcome is None:
                continue
            trigger = due_reminder(route, p, sent.get(p.id, ()), self._policy, now=now)
            if trigger is not None:
                due.append(_Due(p.id, trigger, outcome))
        return due
