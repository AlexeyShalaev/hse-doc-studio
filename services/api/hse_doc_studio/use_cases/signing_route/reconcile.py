"""Сверка маршрута с проектом (docs/design/signing-route.md, разделы 5.5, 12.5 и 12.11).

Маршрут хранит снимок отпечатков документов: версии на подписи, B и видимого слоя. Если проект изменился мимо
маршрута (подмена версии на подписи, B или видимого слоя через git, восстановление, синхронизацию, правку подписей;
уход участника), пересчёт на текущих фактах это замечает и записывает итог: остановку с уведомлениями
(`sent_changed`, `frozen_changed`, `marks_changed`, `participant_left`) или следующий ход, если подпись слота
появилась другим путём. Пересборка и правка исходников меняют только рабочую сборку и маршрут не трогают.

- `RouteRecalculation.recalculate` один пересчёт одного маршрута под блокировкой его строки и `project_lock`.
  Им пользуются сторож других входов подписи (`SigningRouteGate`) и сверка. Маршрут 0.20.0 без версии на подписи
  пересчёт сначала переносит (`RouteMigration`, 12.11): иначе источником была бы текущая сборка.
- `RouteReconciler` сверяет маршруты проекта, идущие и завершённые (хуки изменений, `RouteWatch`), все идущие
  маршруты сервера (периодическая задача лидера) и переносит все маршруты 0.20.0 (разовая задача лидера).

Пересчёт идемпотентный: на тех же фактах второй проход ничего не пишет, поэтому хуки, периодическая сверка и
сценарии маршрута друг другу не мешают. Сценарий маршрута держит строку маршрута до конца своей транзакции:
сверка, попавшая на это время, дождётся её и увидит уже обновлённый снимок.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

import structlog

from hse_doc_studio.core.signatures.plan import CRYPTO_METHODS, method_of
from hse_doc_studio.core.signing_route.audit import RouteAuditAction
from hse_doc_studio.core.signing_route.entities import (
    HOLDING_STATUSES,
    WATCHING_STATUSES,
    DocSlot,
    EventKind,
    RouteEvent,
    RouteStatus,
    SigningRoute,
)
from hse_doc_studio.core.signing_route.signer import unsigned_crypto
from hse_doc_studio.core.signing_route.transitions import apply_evaluation
from hse_doc_studio.use_cases.signing_route.migration import Migration
from hse_doc_studio.use_cases.signing_route.point import RoutePoint
from hse_doc_studio.use_cases.signing_route.scenario import (
    RouteScenario,
    Settled,
    closing_events,
    frozen_events,
    route_files,
)

logger = structlog.get_logger()


class RouteRecalculation(RouteScenario):
    async def recalculate(
        self, project_id: UUID, route_id: UUID, *, signed: Sequence[DocSlot] = (), actor_id: UUID | None = None
    ) -> bool:
        """Пересчитать маршрут на текущих фактах и записать итог; True, если маршрут изменился.

        `signed` слоты, подписи которых только что записаны другим входом (раздел 6.10): в историю идёт событие
        `signed` участника каждого слота, один раз за раунд. `actor_id` тот, чьё действие вызвало пересчёт (None
        у сверки сервера). Вызывать вне `project_lock`: порядок блокировок строка маршрута, затем `project_lock`.
        """
        at = self._s.clock()
        async with self._s.uow.begin():
            route = await self._s.routes.get(project_id, route_id, lock=True)
            if route is None or route.status not in WATCHING_STATUSES:
                return False
            point = await self._s.points.load(project_id, route.profile_id)
            async with route_files(point.project):
                migrated = await self._migrate(point, route, at)
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
                # Ничего не изменилось: повторная сверка маршрут не трогает (версия записи не растёт). Перенос
                # 0.20.0 пишет только файлы и аудит: маршрут и его снимок те же.
                return migrated
            await self._commit(settled, events, actor_id=actor_id, at=at)
            return True

    async def _migrate(self, point: RoutePoint, route: SigningRoute, at: datetime) -> bool:
        """Перенести маршрут 0.20.0 (12.11) под `route_files`; True, если перенос что-то изменил."""
        if self._s.migration is None:
            return False
        migration = await self._s.migration.migrate(point, route, at=at)
        if migration is None:
            return False
        await self._audit_migration(route, migration)
        return True

    async def _audit_migration(self, route: SigningRoute, migration: Migration) -> None:
        await self._audit(RouteAuditAction.migrate, route, actor_id=None, details=migration.audit_details())

    async def _signed_events(
        self, route: SigningRoute, settled: Settled, pairs: Sequence[DocSlot], actor_id: UUID | None
    ) -> list[RouteEvent]:
        """События подписи слотов другим входом: только слот с ЭП, который теперь подписан, и не повторно."""
        if not pairs:
            return []
        at = self._s.clock()
        recorded = [
            (e.participant_id, dict(e.details))
            for e in await self._s.routes.list_events(route.id, round=route.round)
            if e.kind is EventKind.signed
        ]
        events: list[RouteEvent] = []
        for pair in dict.fromkeys(pairs):
            owner = next((p for p in route.participants if pair in p.assignments), None)
            slot = settled.loaded.state.slots.get(pair.slot_id)
            crypto = slot is not None and method_of(slot.sign_mode) in CRYPTO_METHODS
            if owner is None or not crypto or pair in unsigned_crypto(owner, settled.loaded.facts):
                continue
            details = {"doc_id": pair.doc_id, "slot_id": pair.slot_id}
            if (owner.id, details) in recorded:
                # Повторная загрузка подписи того же слота: в истории раунда она уже есть.
                continue
            events.append(
                RouteEvent(
                    route.id, route.round, at, EventKind.signed, actor_id, participant_id=owner.id, details=details
                )
            )
        return events


class RouteReconciler(RouteRecalculation):
    """Сверка маршрутов, которые следят за документами (`WATCHING_STATUSES`)."""

    async def project(self, project_id: UUID) -> int:
        """Сверить маршруты проекта; возвращает, сколько из них изменилось."""
        return await self._reconcile(await self._s.routes.list_watching(project_id))

    async def sweep(self) -> int:
        """Сверить идущие маршруты сервера: страховка на случай пропущенного хука (гибрид, сбой, рестарт).

        Завершённые маршруты проход не трогает: их со временем становится много, а сверка читает PDF каждого
        документа. За ними следят хуки, а чтение маршрута и плана и так показывает вычисленное состояние.
        """
        watching = await self._s.routes.list_watching()
        return await self._reconcile([route for route in watching if route.status is RouteStatus.active])

    async def migrate_all(self) -> int | None:
        """Разовый перенос маршрутов 0.20.0 сервера (12.11); сколько маршрутов изменилось, None при сбое.

        Идущие и завершённые переносит пересчёт (тот же путь, что ленивый перенос в сверке): маршрут без
        восстановимой версии он сразу останавливает. Остановленным и возвращённым снимается только версия на
        подписи. Повтор ничего не меняет, поэтому задачу можно запускать на каждом старте лидера.
        """
        changed, failed = 0, False
        for route in await self._s.routes.list_holding():
            try:
                if route.status in WATCHING_STATUSES:
                    changed += await self.recalculate(route.project_id, route.id)
                else:
                    changed += await self._migrate_held(route.project_id, route.id)
            except Exception:  # noqa: BLE001 — сбой одного маршрута (битый проект, снятый пак) остальным не мешает
                failed = True
                logger.warning("signing route not migrated", route_id=str(route.id), exc_info=True)
        return None if failed else changed

    async def _migrate_held(self, project_id: UUID, route_id: UUID) -> bool:
        """Перенос остановленного или возвращённого маршрута: версия на подписи без пересчёта."""
        at = self._s.clock()
        async with self._s.uow.begin():
            route = await self._s.routes.get(project_id, route_id, lock=True)
            # Пока ждали строку, маршрут могли отправить заново: отправка сама снимает версию на подписи, и
            # переносить уже нечего.
            if route is None or route.status not in HOLDING_STATUSES:
                return False
            point = await self._s.points.load(project_id, route.profile_id)
            async with route_files(point.project):
                return await self._migrate(point, route, at)

    async def _reconcile(self, routes: list[SigningRoute]) -> int:
        changed = 0
        for route in routes:
            try:
                changed += await self.recalculate(route.project_id, route.id)
            except Exception:  # noqa: BLE001 — сбой одного маршрута (битый проект, снятый пак) остальным не мешает
                logger.warning("signing route not reconciled", route_id=str(route.id), exc_info=True)
        return changed
