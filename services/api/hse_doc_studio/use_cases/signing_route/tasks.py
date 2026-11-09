"""«На подпись»: задачи человека по всем проектам (`GET /account/signing-tasks`, docs/design/signing-route.md, 6.6).

Задача это идущий маршрут, где по расчёту на текущих фактах от человека сейчас нужно действие: согласовать,
согласовать и подписать или подписать итоговый PDF. Чтение ничего не пишет: если хук ещё не остановил маршрут после
изменения документа, расчёт уже видит остановку, и задачи нет.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import NextAction, RouteStatus, SigningRoute
from hse_doc_studio.core.signing_route.ports import IRouteFacts, IRouteLabels
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository

_log = logging.getLogger(__name__)

TASK_ACTIONS = frozenset({NextAction.approve, NextAction.approve_and_sign, NextAction.sign})
_ACTIVE = (RouteStatus.active,)


@dataclass(frozen=True)
class SigningTask:
    """Строка «На подпись». `since` время запроса этого раунда (None, если запроса ещё не было);
    `participant_id` участник маршрута, чья это задача."""

    project_id: UUID
    project_name: str
    route_id: UUID
    profile_id: str
    profile_name: Mapping[str, str]
    round: int
    sender: str | None
    deadline: datetime | None
    next_action: NextAction
    since: datetime | None
    participant_id: UUID


@dataclass(frozen=True)
class _Pending:
    route: SigningRoute
    participant_id: UUID
    action: NextAction


class ListSigningTasksUC:
    """Задачи человека; он же счётчик «Входящих» (`ISigningTaskCounter`)."""

    def __init__(
        self,
        routes: ISigningRouteRepository,
        facts: IRouteFacts,
        labels: IRouteLabels,
        users: IUserRepository,
    ) -> None:
        self._routes = routes
        self._facts = facts
        self._labels = labels
        self._users = users

    async def execute(self, user_id: str) -> list[SigningTask]:
        """Срочные первыми: по сроку (без срока в конце), затем кто дольше ждёт."""
        tasks = [await self._task(pending) for pending in await self._pending(user_id)]
        found = [task for task in tasks if task is not None]
        return sorted(found, key=_urgency)

    async def count_for_user(self, user_id: str) -> int:
        return len(await self._pending(user_id))

    async def _pending(self, user_id: str) -> list[_Pending]:
        uid = _uuid(user_id)
        if uid is None:
            return []
        found = [
            await self._pending_in(route, uid) for route in await self._routes.list_for_user(uid, statuses=_ACTIVE)
        ]
        return [pending for pending in found if pending is not None]

    async def _pending_in(self, route: SigningRoute, user_id: UUID) -> _Pending | None:
        """Действие человека в маршруте по расчёту на текущих фактах; None, если ему сейчас нечего делать."""
        mine = route.participants_of(user_id)
        if not mine:
            return None
        try:
            facts = await self._facts.facts(route)
        except Exception:
            # Проект не прочитать (битый файл, снятый пак): задача не показывается, остальные показываются.
            _log.warning("signing route facts unavailable", extra={"route_id": str(route.id)}, exc_info=True)
            return None
        if facts is None:
            return None
        evaluation = evaluate(route, facts)
        if evaluation.status is not RouteStatus.active:
            return None
        for p in mine:
            action = evaluation.participant(p.id).next_action
            if action in TASK_ACTIONS:
                return _Pending(route, p.id, action)
        return None

    async def _task(self, pending: _Pending) -> SigningTask | None:
        route = pending.route
        labels = await self._labels.labels(route.project_id, route.profile_id)
        if labels is None:
            return None
        notified = route.participant(pending.participant_id).notified
        since = notified.at if notified is not None and notified.round == route.round else None
        return SigningTask(
            project_id=route.project_id,
            project_name=labels.project_name,
            route_id=route.id,
            profile_id=route.profile_id,
            profile_name=dict(labels.profile_name),
            round=route.round,
            sender=await self._name(route.sent_by),
            deadline=route.deadline,
            next_action=pending.action,
            since=since,
            participant_id=pending.participant_id,
        )

    async def _name(self, user_id: UUID | None) -> str | None:
        if user_id is None:
            return None
        user = await self._users.get(user_id.hex)
        return user.name if user is not None and user.name.strip() else None


def _uuid(user_id: str) -> UUID | None:
    try:
        return UUID(hex=user_id)
    except ValueError:
        return None


def _urgency(task: SigningTask) -> tuple[bool, float, float]:
    deadline = task.deadline.timestamp() if task.deadline is not None else 0.0
    since = task.since.timestamp() if task.since is not None else 0.0
    return (task.deadline is None, deadline, since)
