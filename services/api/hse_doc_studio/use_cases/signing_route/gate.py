"""Другие входы подписи слота маршрута (docs/design/signing-route.md, раздел 6.10).

Подписант ставит ЭП не только на своей странице ключом Студии: КриптоПро в браузере и готовая подпись идут
существующими адресами плана подписей (`.../docs/{doc}/detached/{slot}`, `.../detached/{slot}/sign`,
`.../embedded/{slot}/sign`). Для них маршрут делает две вещи:

- до записи пускает к слоту идущего маршрута только его участника и только когда маршрут ждёт его подписи
  (`to_sign`), иначе 409 `not_your_turn`;
- после записи пересчитывает маршрут: событие `signed`, запрос следующему шагу, завершение.

Правки подписей документов маршрута (`route_locked`), «Подписать комплект» и хуки сборки и синхронизации это
сторожа и триггеры среза R7; пересчёт для них тот же (`signature_written` без слота тоже годится как сверка).
"""

from __future__ import annotations

from uuid import UUID

import structlog

from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import ActorKind
from hse_doc_studio.core.signatures.plan import CRYPTO_METHODS, method_of
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import (
    WATCHING_STATUSES,
    DocSlot,
    EventKind,
    NextAction,
    RouteConflictError,
    RouteEvent,
    RouteStatus,
    not_your_turn,
)
from hse_doc_studio.core.signing_route.signer import unsigned_crypto
from hse_doc_studio.use_cases.signatures._studio_signer import project_lock
from hse_doc_studio.use_cases.signing_route.scenario import RouteScenario, actor_uuid, closing_events

logger = structlog.get_logger()


def _actor_id() -> UUID | None:
    actor = require_actor()
    if actor.kind is not ActorKind.user or not actor.id:
        return None
    try:
        return actor_uuid(actor)
    except ValueError:
        return None


class SigningRouteGate(RouteScenario):
    """`ISigningRouteGate` сервера."""

    async def require_turn(self, project_id: UUID, doc_id: str, slot_id: str) -> None:
        route = await self._s.routes.holding(project_id, doc_id)
        pair = DocSlot(doc_id, slot_id)
        if route is None or route.status is not RouteStatus.active or pair not in route.pairs:
            return
        point = await self._s.points.load(project_id, route.profile_id)
        loaded = await self._s.facts.load(point, route)
        evaluation = evaluate(route, loaded.facts)
        if evaluation.status is not RouteStatus.active:
            # Маршрут по расчёту уже остановлен или завершён: очереди нет, слот подписывается как без маршрута.
            return
        owner = next(p for p in route.participants if pair in p.assignments)
        if owner.user_id is None or owner.user_id != _actor_id():
            raise not_your_turn()
        if evaluation.participant(owner.id).next_action is not NextAction.sign:
            raise not_your_turn()

    async def signature_written(self, project_id: UUID, doc_id: str, slot_id: str) -> None:
        held = await self._s.routes.holding(project_id, doc_id)
        if held is None or held.status not in WATCHING_STATUSES:
            return
        try:
            await self._recalculate(project_id, held.id, DocSlot(doc_id, slot_id))
        except RouteConflictError:
            # Подпись уже записана в файлы проекта; маршрут догонит её при следующем действии или сверке.
            logger.warning("signing route not recalculated after a signature", route_id=str(held.id), exc_info=True)

    async def _recalculate(self, project_id: UUID, route_id: UUID, pair: DocSlot) -> None:
        at = self._s.clock()
        actor_id = _actor_id()
        async with self._s.uow.begin():
            route = await self._s.routes.get(project_id, route_id, lock=True)
            if route is None or route.status not in WATCHING_STATUSES:
                return
            point = await self._s.points.load(project_id, route.profile_id)
            async with project_lock(point.project):
                loaded = await self._s.facts.load(point, route)
                if await self._stop_if_changed(point, route, loaded, at) is not None:
                    return
                settled = await self._settle(point, route, at, loaded)
            events: list[RouteEvent] = []
            owner = next((p for p in route.participants if pair in p.assignments), None)
            slot = settled.loaded.state.slots.get(pair.slot_id)
            crypto = slot is not None and method_of(slot.sign_mode) in CRYPTO_METHODS
            if owner is not None and crypto and pair not in unsigned_crypto(owner, settled.loaded.facts):
                details = {"doc_id": pair.doc_id, "slot_id": pair.slot_id}
                events.append(
                    RouteEvent(
                        route.id, route.round, at, EventKind.signed, actor_id, participant_id=owner.id, details=details
                    )
                )
            await self._commit(settled, [*events, *closing_events(settled, at)], actor_id=actor_id, at=at)
