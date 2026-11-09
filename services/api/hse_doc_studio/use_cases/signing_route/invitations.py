"""Приглашённый подписант принял приглашение (docs/design/signing-route.md, разделы 5.4 и 6.5).

Сценарий принятия приглашения в своей транзакции вызывает хук (`IInvitationAcceptedHook`). Участники маршрутов
проекта, которые ждали этого приглашения, получают `user_id`; если у идущего маршрута теперь его очередь, он
получает запрос («Входящие» и письмо), а запрос помечается у участника, чтобы расчёт его не повторял.

Остальные эффекты расчёта (фиксация, остановка) хук не выполняет: это файлы проекта, их делают сценарии маршрута
при следующем действии или сверке. Сбой маршрута принятие приглашения не отменяет.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from uuid import UUID

from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import Notice, RouteConflictError, RouteStatus, SigningRoute
from hse_doc_studio.core.signing_route.notices import ISigningNotifier, mark_requests, notices_in
from hse_doc_studio.core.signing_route.ports import IRouteFacts
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository

_log = logging.getLogger(__name__)


class SigningRouteInviteeHook:
    """`IInvitationAcceptedHook` маршрутов подписания."""

    def __init__(
        self,
        routes: ISigningRouteRepository,
        facts: IRouteFacts,
        notifier: ISigningNotifier,
        clock: Clock = utc_now,
    ) -> None:
        self._routes = routes
        self._facts = facts
        self._notifier = notifier
        self._clock = clock

    async def on_invitation_accepted(self, project_id: UUID, invitation_id: str, user_id: str) -> None:
        try:
            uid = UUID(hex=user_id)
        except ValueError:
            return
        for found in await self._routes.list_for_invitation(project_id, invitation_id):
            if found.status is RouteStatus.archived:
                continue
            try:
                await self._bind(project_id, found.id, invitation_id, uid)
            except RouteConflictError:
                # Строка маршрута под блокировкой, так что это почти невозможно. Участник остаётся `invited`,
                # автор увидит это в маршруте; принятие приглашения из-за маршрута не падает.
                _log.warning("signing route invitee not bound", extra={"route_id": str(found.id)}, exc_info=True)

    async def _bind(self, project_id: UUID, route_id: UUID, invitation_id: str, user_id: UUID) -> None:
        route = await self._routes.get(project_id, route_id, lock=True)
        if route is None:
            return
        bound = tuple(p.id for p in route.participants if p.invitation_id == invitation_id and p.user_id is None)
        if not bound:
            return
        for participant_id in bound:
            route = route.with_participant(replace(route.participant(participant_id), user_id=user_id))
        notices = await self._requests(route, bound)
        now = self._clock()
        route = mark_requests(route, notices, at=now)
        route = await self._routes.save(route)
        await self._notifier.deliver(route, notices)

    async def _requests(self, route: SigningRoute, bound: tuple[UUID, ...]) -> tuple[Notify, ...]:
        """Запросы тем, кто только что получил аккаунт, если у идущего маршрута их очередь."""
        if route.status is not RouteStatus.active:
            return ()
        try:
            facts = await self._facts.facts(route)
        except Exception:
            _log.warning("signing route facts unavailable", extra={"route_id": str(route.id)}, exc_info=True)
            return ()
        if facts is None:
            return ()
        return tuple(
            notify
            for notify in notices_in(evaluate(route, facts).effects)
            if notify.notice is Notice.request and set(notify.participant_ids) <= set(bound)
        )
