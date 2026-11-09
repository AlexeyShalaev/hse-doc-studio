"""Общий ход сценариев маршрута (docs/design/signing-route.md, раздел 5.1).

Под блокировкой строки маршрута: переход, `evaluate`, файловые эффекты под `project_lock`, `refresh_snapshot`,
итоговый расчёт, `apply_evaluation`, затем одна транзакция с маршрутом, событиями и уведомлениями и
`mark_notified` для запросов. Здесь то, что одинаково у сценариев автора и подписанта: люди маршрута, доведение
расчёта до неподвижной точки и запись с уведомлениями.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.signatures.plan import slot_persona
from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.engine import Evaluation, evaluate
from hse_doc_studio.core.signing_route.entities import (
    RouteEvent,
    SigningRoute,
)
from hse_doc_studio.core.signing_route.notices import mark_requests
from hse_doc_studio.core.signing_route.ports import IRoutePeople, ISigningNotifier
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.core.signing_route.transitions import apply_evaluation, refresh_snapshot
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.orgs.access import user_id_of
from hse_doc_studio.use_cases.signing_route.effects import RouteFileEffects
from hse_doc_studio.use_cases.signing_route.facts import LoadedFacts, RouteFactsLoader
from hse_doc_studio.use_cases.signing_route.point import RoutePoint, RoutePointLoader
from hse_doc_studio.use_cases.signing_route.views import (
    People,
    PersonaCandidates,
    RouteDetails,
    build_details,
    persona_candidates,
)

# Сколько раз доводить расчёт: эффекты одного прохода (картинки, плашки, фиксация) дают новый, обычно пустой.
_MAX_PASSES = 3


def actor_uuid(actor: Actor) -> UUID:
    """Пользователь-актор как UUID сущностей маршрута (`users.id` это 32 hex-символа)."""
    return UUID(user_id_of(actor))


def route_not_found() -> NotFoundError:
    return NotFoundError(localized_error("Маршрут подписания не найден", "Signing route not found"))


@dataclass(frozen=True)
class Settled:
    """Маршрут после файловых эффектов и обновления снимка, факты и итоговый расчёт на них."""

    route: SigningRoute
    loaded: LoadedFacts
    evaluation: Evaluation
    frozen: tuple[str, ...] = ()

    @property
    def notices(self) -> tuple[Notify, ...]:
        return tuple(e for e in self.evaluation.effects if isinstance(e, Notify))


@dataclass(frozen=True)
class RouteServices:
    """Порты, нужные любому сценарию маршрута."""

    routes: ISigningRouteRepository
    points: RoutePointLoader
    facts: RouteFactsLoader
    effects: RouteFileEffects
    people: IRoutePeople
    notifier: ISigningNotifier
    uow: IUnitOfWork
    access: IProjectAccessChecker
    clock: Clock = utc_now


class RouteScenario:
    def __init__(self, services: RouteServices) -> None:
        self._s = services

    async def _get(self, project_id: UUID, route_id: UUID, *, lock: bool = False) -> SigningRoute:
        route = await self._s.routes.get(project_id, route_id, lock=lock)
        if route is None:
            raise route_not_found()
        return route

    async def _people(self, project_id: UUID, route: SigningRoute, loaded: LoadedFacts) -> People:
        users = {p.user_id for p in route.participants if p.user_id is not None}
        users |= {u for u in (route.sent_by, route.created_by) if u is not None}
        invitees = {i.invitation_id: i for i in await self._s.people.invitees(project_id)}
        return People(names=await self._s.people.names(users), invitees=invitees, personas=loaded.personas)

    async def _manages(self, project_id: UUID) -> bool:
        """Вправе ли актор управлять маршрутом точки (`SUBMISSION_CREATE`)."""
        try:
            await self._s.access.require(project_id, Action.SUBMISSION_CREATE)
        except (NotFoundError, ProjectForbiddenError):
            return False
        return True

    async def _details(self, actor: Actor, point: RoutePoint, route: SigningRoute) -> RouteDetails:
        loaded = await self._s.facts.load(point, route)
        evaluation = evaluate(route, loaded.facts)
        events = await self._s.routes.list_events(route.id)
        people = await self._people(point.project_id, route, loaded)
        actor_id = actor_uuid(actor) if actor.kind is ActorKind.user else None
        names = dict(people.names)
        missing = {e.actor_id for e in events if e.actor_id is not None and e.actor_id not in names}
        if missing:
            names |= await self._s.people.names(missing)
            people = People(names=names, invitees=people.invitees, personas=people.personas)
        manages = await self._manages(point.project_id)
        show = manages or any(p.user_id == actor_id for p in route.participants)
        details = build_details(point, route, loaded.facts, evaluation, people, events, show_comments=show)
        if not manages:
            return details
        return replace(details, candidates=await self._candidates(point, route))

    async def _candidates(self, point: RoutePoint, route: SigningRoute) -> tuple[PersonaCandidates, ...]:
        """Персоны участников, слотов точки и необязательных слотов её документов, с людьми проекта на каждую."""
        personas = [
            *(p.persona for p in route.participants),
            *(slot_persona(pair.slot_id) for pair in (*point.required, *point.optional_pairs())),
        ]
        candidates = await self._s.people.candidates(point.project_id)
        invitees = await self._s.people.invitees(point.project_id)
        return persona_candidates(personas, candidates, invitees)

    async def _settle(
        self, point: RoutePoint, route: SigningRoute, at: datetime, loaded: LoadedFacts | None = None
    ) -> Settled:
        """Выполнить файловые эффекты расчёта, пока они есть; вызывать под `project_lock`.

        `loaded` факты, на которых маршрут получен (переход); без них факты читаются заново и снимок обновляется,
        потому что перед этим файлы менял сам маршрут или подписант на своей странице.
        """
        if loaded is None:
            loaded = await self._s.facts.load(point, route)
            route = refresh_snapshot(route, loaded.facts)
        evaluation = evaluate(route, loaded.facts)
        frozen: list[str] = []
        for _ in range(_MAX_PASSES):
            files = [e for e in evaluation.effects if not isinstance(e, Notify)]
            if not files:
                break
            frozen += await self._s.effects.apply(point, route, files, at=at)
            loaded = await self._s.facts.load(point, route)
            route = refresh_snapshot(route, loaded.facts)
            evaluation = evaluate(route, loaded.facts)
        return Settled(route, loaded, evaluation, tuple(frozen))

    async def _commit(
        self,
        settled: Settled,
        events: Sequence[RouteEvent],
        *,
        actor_id: UUID | None,
        at: datetime,
        comment: str | None = None,
    ) -> SigningRoute:
        """Статус по расчёту, отметки запросов, запись маршрута с событиями и уведомления в одной транзакции."""
        notices = settled.notices
        route = mark_requests(apply_evaluation(settled.route, settled.evaluation, at=at), notices, at=at)
        saved = await self._s.routes.save(route, events=events)
        await self.notify(saved, notices, actor_id=actor_id, comment=comment)
        return saved

    async def notify(
        self, route: SigningRoute, notices: Sequence[Notify], *, actor_id: UUID | None, comment: str | None = None
    ) -> None:
        wanted = [n for n in notices if n.participant_ids or n.sender]
        if wanted:
            await self._s.notifier.notify(route, wanted, actor_id=actor_id, comment=comment)
