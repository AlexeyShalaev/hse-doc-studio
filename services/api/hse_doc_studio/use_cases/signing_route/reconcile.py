"""Сверка маршрута с проектом (docs/design/signing-route.md, раздел 5.5).

Маршрут хранит снимок отпечатков документов. Если проект изменился мимо маршрута (пересборка, правка подписей,
синхронизация, восстановление из истории, уход участника), пересчёт на текущих фактах это замечает и записывает
итог: остановку с уведомлениями или следующий ход, если подпись слота появилась другим путём.

- `RouteRecalculation.recalculate` один пересчёт одного маршрута под блокировкой его строки и `project_lock`.
  Им пользуются сторож других входов подписи (`SigningRouteGate`) и сверка.
- `RouteReconciler` сверяет маршруты проекта (хуки изменений, `RouteWatch`) и все маршруты сервера
  (периодическая задача лидера).

Пересчёт идемпотентный: на тех же фактах второй проход ничего не пишет, поэтому хуки, периодическая сверка и
сценарии маршрута друг другу не мешают. Сценарий маршрута, который сам пишет файлы проекта, держит строку
маршрута до конца своей транзакции: сверка, вызванная его же записью, дождётся её и увидит уже обновлённый снимок.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from hse_doc_studio.core.signatures.plan import CRYPTO_METHODS, method_of
from hse_doc_studio.core.signing_route.entities import (
    WATCHING_STATUSES,
    DocSlot,
    EventKind,
    RouteEvent,
    SigningRoute,
)
from hse_doc_studio.core.signing_route.signer import unsigned_crypto
from hse_doc_studio.core.signing_route.transitions import apply_evaluation
from hse_doc_studio.use_cases.signatures._studio_signer import project_lock
from hse_doc_studio.use_cases.signing_route.scenario import RouteScenario, Settled, closing_events, frozen_events

logger = structlog.get_logger()


class RouteRecalculation(RouteScenario):
    async def recalculate(
        self, project_id: UUID, route_id: UUID, *, signed: DocSlot | None = None, actor_id: UUID | None = None
    ) -> bool:
        """Пересчитать маршрут на текущих фактах и записать итог; True, если маршрут изменился.

        `signed` слот, подпись которого только что записана другим входом (раздел 6.10): в историю идёт событие
        `signed` его участника, один раз за раунд. `actor_id` тот, чьё действие вызвало пересчёт (None у сверки
        сервера). Вызывать вне `project_lock`: порядок блокировок строка маршрута, затем `project_lock`.
        """
        at = self._s.clock()
        async with self._s.uow.begin():
            route = await self._s.routes.get(project_id, route_id, lock=True)
            if route is None or route.status not in WATCHING_STATUSES:
                return False
            point = await self._s.points.load(project_id, route.profile_id)
            async with project_lock(point.project):
                loaded = await self._s.facts.load(point, route)
                if await self._stop_if_changed(point, route, loaded, at) is not None:
                    return True
                settled = await self._settle(point, route, at, loaded)
            events = [
                *await self._signed_events(route, settled, signed, actor_id),
                *frozen_events(settled, at),
                *closing_events(settled, at),
            ]
            if (
                not events
                and not settled.notices
                and apply_evaluation(settled.route, settled.evaluation, at=at) == route
            ):
                # Ничего не изменилось: повторная сверка маршрут не трогает (версия записи не растёт).
                return False
            await self._commit(settled, events, actor_id=actor_id, at=at)
            return True

    async def _signed_events(
        self, route: SigningRoute, settled: Settled, pair: DocSlot | None, actor_id: UUID | None
    ) -> list[RouteEvent]:
        """Событие подписи слота другим входом: только слот с ЭП, который теперь подписан, и не повторно."""
        if pair is None:
            return []
        owner = next((p for p in route.participants if pair in p.assignments), None)
        slot = settled.loaded.state.slots.get(pair.slot_id)
        crypto = slot is not None and method_of(slot.sign_mode) in CRYPTO_METHODS
        if owner is None or not crypto or pair in unsigned_crypto(owner, settled.loaded.facts):
            return []
        details = {"doc_id": pair.doc_id, "slot_id": pair.slot_id}
        for earlier in await self._s.routes.list_events(route.id, round=route.round):
            if earlier.kind is EventKind.signed and earlier.participant_id == owner.id and earlier.details == details:
                # Повторная загрузка той же подписи: в истории раунда она уже есть.
                return []
        at = self._s.clock()
        return [
            RouteEvent(route.id, route.round, at, EventKind.signed, actor_id, participant_id=owner.id, details=details)
        ]


class RouteReconciler(RouteRecalculation):
    """Сверка маршрутов, которые следят за документами (`WATCHING_STATUSES`)."""

    async def project(self, project_id: UUID) -> int:
        """Сверить маршруты проекта; возвращает, сколько из них изменилось."""
        return await self._reconcile(await self._s.routes.list_watching(project_id))

    async def sweep(self) -> int:
        """Сверить все маршруты сервера: страховка на случай пропущенного хука (гибрид, сбой, рестарт)."""
        return await self._reconcile(await self._s.routes.list_watching())

    async def _reconcile(self, routes: list[SigningRoute]) -> int:
        changed = 0
        for route in routes:
            try:
                changed += await self.recalculate(route.project_id, route.id)
            except Exception:  # noqa: BLE001 — сбой одного маршрута (битый проект, снятый пак) остальным не мешает
                logger.warning("signing route not reconciled", route_id=str(route.id), exc_info=True)
        return changed
