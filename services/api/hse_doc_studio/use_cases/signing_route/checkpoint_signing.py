"""Состояние подписания точки для напоминания о сроке (docs/design/signing-route.md, 16.7).

Напоминание `checkpoint_due` говорит автору, где подписание: «ждём научного руководителя (Иванов И. И.)»,
«завершено» или «не отправлено». Маршрут точки: незавершённый, если есть, иначе самый новый; снятые с контроля
(`archived`) не считаются, и без маршрута строки нет. Идущий и завершённый маршрут считается на текущих фактах, как
его видят экраны: документ изменился, и маршрут по расчёту уже остановлен, значит «не отправлено». Ждём тех, чья
очередь по расчёту, и приглашённых, кто ещё не принял приглашение; имя берётся из аккаунта. Только читает.
"""

from __future__ import annotations

from uuid import UUID

from hse_doc_studio.core.checkpoint_reminders import AwaitedSigner, CheckpointSigning, SigningState
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import (
    OPEN_STATUSES,
    TURN_STATES,
    WATCHING_STATUSES,
    ParticipantState,
    RouteStatus,
)
from hse_doc_studio.core.signing_route.ports import IRouteFacts
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository

_AWAITED = frozenset({*TURN_STATES, ParticipantState.invited})
_COUNTED = frozenset(RouteStatus) - {RouteStatus.archived}


class CheckpointSigningReader:
    """`ICheckpointSigning` сервера."""

    def __init__(self, routes: ISigningRouteRepository, facts: IRouteFacts, users: IUserRepository) -> None:
        self._routes = routes
        self._facts = facts
        self._users = users

    async def signing(self, project_id: UUID, profile_id: str) -> CheckpointSigning | None:
        routes = await self._routes.list_for_project(project_id, profile_id=profile_id, statuses=_COUNTED)
        if not routes:
            return None
        route = next((r for r in routes if r.status in OPEN_STATUSES), routes[0])
        if route.status not in WATCHING_STATUSES:
            return CheckpointSigning(SigningState.not_sent)
        facts = await self._facts.facts(route)
        if facts is None:
            # Проект или пак не прочитать: по хранимому статусу, без имён.
            return _by_status(route.status)
        evaluation = evaluate(route, facts)
        if evaluation.status is RouteStatus.completed:
            return CheckpointSigning(SigningState.completed)
        if evaluation.status is not RouteStatus.active:
            return CheckpointSigning(SigningState.not_sent)
        awaited = [p for p in route.participants if evaluation.participant(p.id).state in _AWAITED]
        return CheckpointSigning(
            SigningState.waiting, tuple([AwaitedSigner(p.persona, await self._name(p.user_id)) for p in awaited])
        )

    async def _name(self, user_id: UUID | None) -> str | None:
        if user_id is None:
            return None
        user = await self._users.get(user_id.hex)
        return (user.name.strip() or None) if user is not None else None


def _by_status(status: RouteStatus) -> CheckpointSigning:
    if status is RouteStatus.completed:
        return CheckpointSigning(SigningState.completed)
    return CheckpointSigning(SigningState.waiting if status is RouteStatus.active else SigningState.not_sent)
