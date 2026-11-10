"""Маршрут у входов мимо страницы подписи (docs/design/signing-route.md, разделы 5.5, 6.1 и 6.10).

Подписант ставит ЭП не только на своей странице ключом Студии: КриптоПро в браузере и готовая подпись идут
существующими адресами плана подписей (`.../docs/{doc}/detached/{slot}`, `.../detached/{slot}/sign`,
`.../embedded/{slot}/sign`), а ещё есть «Подписать комплект» и `sign_submission`. Для них маршрут:

- до записи пускает к слоту идущего маршрута только его участника и только когда маршрут ждёт его подписи
  (`to_sign`), иначе 409 `not_your_turn`; «Подписать комплект» спрашивает то же про документ целиком (`hold`);
- после записи пересчитывает маршрут: событие `signed`, запрос следующему шагу, завершение.

Правки подписей документа идущего маршрута (размещения, настройка и картинка слота, подписант плашки, фиксация и
её снятие, удаление открепленной подписи) закрыты: 409 `route_locked`. Маршрут, который по расчёту уже остановлен
или завершён, ни очередь, ни правки не держит: остановку запишет сверка (`reconcile.py`).

План подписей получает отсюда маршрут и состояния участников (`plan_routes`); чтение ничего не пишет.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

import structlog

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.signing_route.engine import Evaluation, evaluate
from hse_doc_studio.core.signing_route.entities import (
    HOLDING_STATUSES,
    WATCHING_STATUSES,
    DocSlot,
    NextAction,
    ParticipantState,
    RouteConflictError,
    RouteStatus,
    SigningRoute,
    not_your_turn,
    route_holds_doc,
    route_locked,
)
from hse_doc_studio.core.signing_route.ports import PlanRoute, PlanRoutes, RouteHold
from hse_doc_studio.core.signing_route.signer import unsigned_crypto
from hse_doc_studio.use_cases.signing_route.facts import LoadedFacts
from hse_doc_studio.use_cases.signing_route.reconcile import RouteRecalculation
from hse_doc_studio.use_cases.signing_route.scenario import actor_uuid
from hse_doc_studio.use_cases.signing_route.watch import expect_recalculation, recalculation_done

logger = structlog.get_logger()


def _actor_id() -> UUID | None:
    actor = current_actor()
    if actor is None or actor.kind is not ActorKind.user or not actor.id:
        return None
    try:
        return actor_uuid(actor)
    except ValueError:
        return None


def _reads_routes() -> bool:
    """Ход маршрута видит вошедший участник проекта: гостю и открывшему проект по ссылке маршрута нет (раздел 7)."""
    actor = current_actor()
    return actor is not None and actor.kind is ActorKind.user and actor.link_id is None


class SigningRouteGate(RouteRecalculation):
    """`ISigningRouteGate` сервера."""

    async def require_turn(self, project_id: UUID, doc_id: str, slot_id: str) -> UUID | None:
        route = await self._s.routes.holding(project_id, doc_id)
        pair = DocSlot(doc_id, slot_id)
        if route is None or route.status is not RouteStatus.active or pair not in route.pairs:
            return None
        calc = await self._going(route)
        if calc is None:
            # Маршрут по расчёту уже остановлен или завершён: очереди нет, слот подписывается как без маршрута.
            return None
        _, evaluation = calc
        owner = next(p for p in route.participants if pair in p.assignments)
        if owner.user_id is None or owner.user_id != _actor_id():
            raise not_your_turn()
        if evaluation.participant(owner.id).next_action is not NextAction.sign:
            raise not_your_turn()
        # Подпись слота маршрута: маршрут пересчитает `signature_written`, сверка по хуку записи не нужна.
        expect_recalculation()
        return route.id

    async def signature_written(self, project_id: UUID, doc_id: str, slot_id: str) -> None:
        await self.signatures_written(project_id, [DocSlot(doc_id, slot_id)])

    async def signatures_written(self, project_id: UUID, slots: Sequence[DocSlot]) -> None:
        recalculation_done()
        signed: dict[UUID, list[DocSlot]] = {}
        for pair in slots:
            held = await self._s.routes.holding(project_id, pair.doc_id)
            if held is not None and held.status in WATCHING_STATUSES:
                signed.setdefault(held.id, []).append(pair)
        for route_id, pairs in signed.items():
            try:
                await self.recalculate(project_id, route_id, signed=pairs, actor_id=_actor_id())
            except RouteConflictError:
                # Подписи уже записаны в файлы проекта; маршрут догонит их при следующем действии или сверке.
                logger.warning(
                    "signing route not recalculated after a signature", route_id=str(route_id), exc_info=True
                )

    async def require_unlocked(
        self, project_id: UUID, *, doc_id: str | None = None, slot_id: str | None = None
    ) -> None:
        if doc_id is not None:
            held = await self._s.routes.holding(project_id, doc_id)
            if held is not None and held.status is RouteStatus.active and await self._going(held) is not None:
                raise route_locked()
        if slot_id is None:
            return
        for route in await self._s.routes.list_for_project(project_id, statuses={RouteStatus.active}):
            calc = await self._going(route)
            if calc is not None and _slot_on_route(route, calc[0], slot_id):
                raise route_locked()

    async def require_not_held(self, project_id: UUID, doc_id: str) -> None:
        if await self._s.routes.holding(project_id, doc_id) is not None:
            raise route_holds_doc()

    async def hold(self, project_id: UUID, doc_id: str) -> RouteHold | None:
        route = await self._s.routes.holding(project_id, doc_id)
        if route is None or route.status is not RouteStatus.active:
            return None
        calc = await self._going(route)
        if calc is None:
            return None
        loaded, evaluation = calc
        actor_id = _actor_id()
        signable = frozenset(
            pair.slot_id
            for p in route.participants
            if actor_id is not None and p.user_id == actor_id
            if evaluation.participant(p.id).next_action is NextAction.sign
            for pair in unsigned_crypto(p, loaded.facts)
            if pair.doc_id == doc_id
        )
        if signable:
            # «Подписать комплект» подпишет слоты маршрута и пересчитает его сам (`signatures_written`).
            expect_recalculation()
        return RouteHold(route.id, route.profile_id, signable)

    async def plan_routes(
        self, project_id: UUID, *, profile_id: str | None = None, doc_id: str | None = None
    ) -> PlanRoutes:
        if not _reads_routes():
            return PlanRoutes()
        shown: PlanRoute | None = None
        states: dict[DocSlot, ParticipantState] = {}
        held: set[str] = set()
        for route in await self._s.routes.list_for_project(project_id, statuses=HOLDING_STATUSES):
            calc = await self._evaluated(route)
            if calc is None:
                continue
            _, evaluation = calc
            states.update(_slot_states(route, evaluation))
            if route.status is RouteStatus.active and evaluation.status is RouteStatus.active:
                held.update(route.docs)
            wanted = route.profile_id == profile_id if profile_id is not None else doc_id in route.docs
            if shown is None and wanted:
                shown = _plan_route(route, evaluation)
        return PlanRoutes(route=shown, slot_states=states, held_docs=frozenset(held))

    async def _evaluated(self, route: SigningRoute) -> tuple[LoadedFacts, Evaluation] | None:
        """Расчёт маршрута на текущих фактах; None, если точку сдачи уже не прочитать (проект или пак сняты)."""
        try:
            point = await self._s.points.load(route.project_id, route.profile_id)
        except NotFoundError:
            return None
        loaded = await self._s.facts.load(point, route)
        return loaded, evaluate(route, loaded.facts)

    async def _going(self, route: SigningRoute) -> tuple[LoadedFacts, Evaluation] | None:
        """Расчёт идущего маршрута; None, если по расчёту он уже не идёт (остановлен, завершён)."""
        calc = await self._evaluated(route)
        if calc is None or calc[1].status is not RouteStatus.active:
            return None
        return calc


def _slot_states(route: SigningRoute, evaluation: Evaluation) -> dict[DocSlot, ParticipantState]:
    """Состояние участника маршрута по каждой его паре «документ, слот»."""
    return {pair: evaluation.participant(p.id).state for p in route.participants for pair in p.assignments}


def _slot_on_route(route: SigningRoute, loaded: LoadedFacts, slot_id: str) -> bool:
    """Слот входит в маршрут или стоит на его документе: правка слота меняет видимый слой документа маршрута."""
    if any(pair.slot_id == slot_id for pair in route.pairs):
        return True
    placements = loaded.state.placements
    return any(
        (placement := placements.get(doc_id, {}).get(slot_id)) is not None and placement.enabled
        for doc_id in route.docs
    )


def _plan_route(route: SigningRoute, evaluation: Evaluation) -> PlanRoute:
    active = evaluation.status is RouteStatus.active
    return PlanRoute(
        id=route.id,
        profile_id=route.profile_id,
        status=evaluation.status,
        phase=evaluation.phase,
        round=route.round,
        current_step=evaluation.step_position if active else None,
        steps_total=len(route.steps),
        stop_reason=evaluation.stop or route.stop_reason,
    )
