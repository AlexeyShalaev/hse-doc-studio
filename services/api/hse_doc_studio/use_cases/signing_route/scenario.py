"""Общий ход сценариев маршрута (docs/design/signing-route.md, раздел 5.1).

Под блокировкой строки маршрута: переход, `evaluate`, файловые эффекты под `project_lock`, `refresh_snapshot`,
итоговый расчёт, `apply_evaluation`, затем одна транзакция с маршрутом, событиями и уведомлениями и
`mark_notified` для запросов. Здесь то, что одинаково у сценариев автора и подписанта: люди маршрута, доведение
расчёта до неподвижной точки и запись с уведомлениями.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor, ActorKind
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.signatures.plan import slot_persona
from hse_doc_studio.core.signing_route.audit import RouteAuditAction, record_of
from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.engine import Evaluation, evaluate
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    EventKind,
    NextAction,
    Notice,
    Participant,
    RequestOutcome,
    RouteEvent,
    RouteStatus,
    SigningRoute,
)
from hse_doc_studio.core.signing_route.notices import mark_requests
from hse_doc_studio.core.signing_route.ports import IRoutePeople, ISigningNotifier
from hse_doc_studio.core.signing_route.repositories import ISigningRouteRepository
from hse_doc_studio.core.signing_route.transitions import apply_evaluation, refresh_snapshot
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.orgs.access import user_id_of
from hse_doc_studio.use_cases.signatures._studio_signer import project_lock
from hse_doc_studio.use_cases.signing_route.audit import SigningRouteAudit
from hse_doc_studio.use_cases.signing_route.effects import RouteFileEffects
from hse_doc_studio.use_cases.signing_route.facts import LoadedFacts, RouteFactsLoader
from hse_doc_studio.use_cases.signing_route.migration import RouteMigration
from hse_doc_studio.use_cases.signing_route.point import RoutePoint, RoutePointLoader
from hse_doc_studio.use_cases.signing_route.preset import route_preset
from hse_doc_studio.use_cases.signing_route.views import (
    People,
    PersonaCandidates,
    RouteDetails,
    build_details,
    persona_candidates,
)
from hse_doc_studio.use_cases.signing_route.watch import own_writes

# Сколько раз доводить расчёт: эффекты одного прохода (картинки, плашки, фиксация) дают новый, обычно пустой.
_MAX_PASSES = 3


@asynccontextmanager
async def route_files(project: Project) -> AsyncIterator[None]:
    """`project_lock` сценария маршрута: файлы проекта пишутся по очереди, а свои записи состояния подписей
    сверку маршрутов не зовут (сценарий держит строку маршрута и сам обновляет снимок, раздел 5.5)."""
    async with project_lock(project):
        with own_writes():
            yield


def actor_uuid(actor: Actor) -> UUID:
    """Пользователь-актор как UUID сущностей маршрута (`users.id` это 32 hex-символа)."""
    return UUID(user_id_of(actor))


def current_actor_uuid() -> UUID | None:
    """Вошедший пользователь текущего запроса как UUID маршрута; None у сервера, токена без пользователя и прочих."""
    actor = current_actor()
    if actor is None or actor.kind is not ActorKind.user or not actor.id:
        return None
    try:
        return actor_uuid(actor)
    except ValueError:
        return None


def route_not_found() -> NotFoundError:
    return NotFoundError(localized_error("Маршрут подписания не найден", "Signing route not found"))


@dataclass(frozen=True)
class Settled:
    """Маршрут после файловых эффектов и обновления снимка, факты и итоговый расчёт на них.

    `frozen` документы, которые маршрут зафиксировал; `reset` пары, чьи ЭП эта фиксация сбросила (новый B).
    """

    route: SigningRoute
    loaded: LoadedFacts
    evaluation: Evaluation
    frozen: tuple[str, ...] = ()
    reset: tuple[DocSlot, ...] = ()

    @property
    def notices(self) -> tuple[Notify, ...]:
        return tuple(e for e in self.evaluation.effects if isinstance(e, Notify))


def dropped_signatures(before: SignaturesState, after: SignaturesState, docs: Sequence[str]) -> tuple[DocSlot, ...]:
    """ЭП документов `docs`, которых после фиксации больше нет: открепленные и встроенные над прежним B."""
    dropped: list[DocSlot] = []
    for doc_id in dict.fromkeys(docs):
        had = {*before.detached.get(doc_id, {}), *before.embedded.get(doc_id, {})}
        kept = {*after.detached.get(doc_id, {}), *after.embedded.get(doc_id, {})}
        dropped += [DocSlot(doc_id, slot_id) for slot_id in sorted(had - kept)]
    return tuple(dropped)


def resign_requests(settled: Settled, notices: Sequence[Notify]) -> tuple[Notify, ...]:
    """Повторный запрос «Подпишите итоговый PDF» владельцам сброшенных ЭП (14.6).

    Запрос `sign` приходит раз за раунд (5.4), поэтому после перефиксации маршрут сам его не повторил бы. Владелец
    подписи, которого расчёт снова ждёт (`sign`), получает запрос с отпечатком нового B в ключе повтора
    (`Notify.again`); кому этот же проход уже шлёт запрос, второй не нужен.
    """
    route, evaluation = settled.route, settled.evaluation
    asked = {pid for n in notices if n.notice is Notice.request for pid in n.participant_ids}
    requests: dict[UUID, Notify] = {}
    for pair in settled.reset:
        owner = next((p for p in route.participants if pair in p.assignments), None)
        frozen = settled.loaded.state.frozen.get(pair.doc_id)
        if owner is None or frozen is None or owner.id in asked or owner.id in requests:
            continue
        if evaluation.participant(owner.id).next_action is not NextAction.sign:
            continue
        requests[owner.id] = Notify(Notice.request, (owner.id,), outcome=RequestOutcome.sign, again=frozen.sha256[:12])
    return tuple(requests.values())


def closing_events(settled: Settled, at: datetime) -> list[RouteEvent]:
    """Событие завершения, если после действия всё уже сделано."""
    route = settled.route
    if settled.evaluation.status is RouteStatus.completed and route.status is not RouteStatus.completed:
        return [RouteEvent(route.id, route.round, at, EventKind.completed)]
    return []


def frozen_events(settled: Settled, at: datetime) -> list[RouteEvent]:
    """Событие фиксации документов маршрутом (без актора: фиксирует сервер)."""
    route = settled.route
    if not settled.frozen:
        return []
    return [RouteEvent(route.id, route.round, at, EventKind.frozen, details={"docs": list(settled.frozen)})]


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
    # Журнал аудита сервера; события истории маршрута пишет в него само хранилище (`AuditedSigningRoutes`).
    audit: SigningRouteAudit | None = None
    # Перенос маршрутов 0.20.0 на версию на подписи (12.11); без него сверка маршруты не переносит.
    migration: RouteMigration | None = None


class RouteScenario:
    def __init__(self, services: RouteServices) -> None:
        self._s = services

    async def _get(self, project_id: UUID, route_id: UUID, *, lock: bool = False) -> SigningRoute:
        route = await self._s.routes.get(project_id, route_id, lock=lock)
        if route is None:
            raise route_not_found()
        return route

    async def _audit(
        self,
        action: RouteAuditAction,
        route: SigningRoute,
        *,
        actor_id: UUID | None,
        participant: Participant | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        """Запись журнала аудита о действии, у которого нет события истории маршрута (раздел 6.7)."""
        if self._s.audit is not None:
            record = record_of(action, route, actor_id=actor_id, participant=participant, details=details)
            await self._s.audit.write(route, record)

    async def _people(self, project_id: UUID, route: SigningRoute, loaded: LoadedFacts) -> People:
        users = {p.user_id for p in route.participants if p.user_id is not None}
        users |= {u for u in (route.sent_by, route.created_by) if u is not None}
        invitees = {i.invitation_id: i for i in await self._s.people.invitees(project_id)}
        return People(names=await self._s.people.names(users), invitees=invitees, personas=loaded.personas)

    async def _people_of(
        self, project_id: UUID, route: SigningRoute, loaded: LoadedFacts, events: Sequence[RouteEvent]
    ) -> People:
        """Люди маршрута и те, кто в нём действовал (акторы событий), чтобы события было кем подписать."""
        people = await self._people(project_id, route, loaded)
        missing = {e.actor_id for e in events if e.actor_id is not None and e.actor_id not in people.names}
        if not missing:
            return people
        names = {**people.names, **await self._s.people.names(missing)}
        return People(names=names, invitees=people.invitees, personas=people.personas)

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
        people = await self._people_of(point.project_id, route, loaded, events)
        actor_id = actor_uuid(actor) if actor.kind is ActorKind.user else None
        manages = await self._manages(point.project_id)
        show = manages or any(p.user_id == actor_id for p in route.participants)
        details = build_details(
            point, route, loaded.facts, evaluation, people, events, show_comments=show, preset=route_preset(point)
        )
        if not manages:
            return details
        return replace(details, candidates=await self._candidates(point, route), manages=True)

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
        before = loaded.state
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
        reset = dropped_signatures(before, loaded.state, frozen)
        return Settled(route, loaded, evaluation, tuple(frozen), reset)

    async def _migrate(self, point: RoutePoint, route: SigningRoute, at: datetime) -> bool:
        """Перенести маршрут 0.20.0 на версию на подписи (12.11) до чтения фактов; True, если перенос что-то изменил.

        Вызывать под блокировкой строки маршрута и `route_files`. Без переноса источником подписи маршрута 0.20.0
        была бы текущая сборка, и первое же действие после пересборки остановило бы маршрут. Аудит
        `signing_route.migrate` без актора: переносит сервер, а не тот, чьё действие пришлось на перенос.
        """
        if self._s.migration is None:
            return False
        migration = await self._s.migration.migrate(point, route, at=at)
        if migration is None:
            return False
        await self._audit(RouteAuditAction.migrate, route, actor_id=None, details=migration.audit_details())
        return True

    async def _stop_if_changed(
        self, point: RoutePoint, route: SigningRoute, loaded: LoadedFacts, at: datetime
    ) -> SigningRoute | None:
        """Остановить маршрут, если расчёт на текущих фактах его останавливает (таблица 5.5, уход участника).

        Возвращает записанный остановленный маршрут или None, если маршрут идёт дальше. Вызывать под блокировкой
        строки маршрута и `project_lock`, в транзакции сценария. Эффекты остановки (придержать картинки, чьё
        согласие относится к прежней сборке) выполняются без обновления снимка: расхождение со снимком это и есть
        причина остановки, а «Отправить заново» снимет новый.
        """
        evaluation = evaluate(route, loaded.facts)
        if evaluation.stop is None:
            return None
        files = [e for e in evaluation.effects if not isinstance(e, Notify)]
        if files:
            await self._s.effects.apply(point, route, files, at=at)
        event = RouteEvent(route.id, route.round, at, EventKind.paused, details={"reason": evaluation.stop.value})
        return await self._commit(Settled(route, loaded, evaluation), [event], actor_id=None, at=at)

    async def _commit(
        self,
        settled: Settled,
        events: Sequence[RouteEvent],
        *,
        actor_id: UUID | None,
        at: datetime,
        comment: str | None = None,
        extra: Sequence[Notify] = (),
    ) -> SigningRoute:
        """Статус по расчёту, отметки запросов, запись маршрута с событиями и уведомления в одной транзакции.

        `extra` уведомления сценария сверх расчёта (новая версия, 12.6). Владельцы ЭП, которые сбросила
        перефиксация, получают запрос подписи заново (`resign_requests`, 14.6)."""
        notices = (*settled.notices, *extra)
        notices = (*notices, *resign_requests(settled, notices))
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
