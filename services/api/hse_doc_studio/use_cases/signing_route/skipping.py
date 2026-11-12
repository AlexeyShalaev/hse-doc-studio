"""«Пропустить» участника маршрута: сценарий автора (docs/design/signing-route.md, 13.3, 13.5 и 13.6).

Права (`SUBMISSION_CREATE`) проверяет гард маршрута по таблице `ROUTE_ACTIONS`. Ход: блокировка строки маршрута,
`project_lock` с пометкой `route_files`, перенос маршрута 0.20.0, факты, переход `transitions.skip`, затем обычный
`_settle` (он выполняет `Skip`, перефиксацию документов и обновляет снимок) и одна транзакция с маршрутом,
событием `skipped` и уведомлениями: пропущенному `signing_skipped`, следующему шагу запрос, автору «Подпишите
итоговый PDF» или завершение.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signing_route.effects import Notify
from hse_doc_studio.core.signing_route.entities import EventKind, Notice, RouteConflictError, RouteEvent, SigningRoute
from hse_doc_studio.core.signing_route.transitions import skip
from hse_doc_studio.use_cases.signing_route.scenario import (
    RouteScenario,
    actor_uuid,
    closing_events,
    frozen_events,
    route_files,
)
from hse_doc_studio.use_cases.signing_route.views import RouteDetails


class SigningRouteSkipping(RouteScenario):
    """«Пропустить» подписанта, для которого все оставшиеся подписи на точке необязательны."""

    async def skip(self, actor: Actor, project_id: UUID, route_id: UUID, participant_id: UUID) -> RouteDetails:
        """Пропустить участника, чья очередь дошла. Отказ: 404 у чужого id, 409 `invalid_transition` у маршрута не в
        `active` (и у такого, который расчёт сейчас остановит), `participant_not_skippable` с причиной.

        Если между показом кнопки и нажатием подписант успел подписать, пропускаются только оставшиеся пары; если
        не осталось ни одной, отказ `done`.
        """
        actor_id = actor_uuid(actor)
        at = self._s.clock()
        refusal: RouteConflictError | None = None
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            route.participant(participant_id)
            point = await self._s.points.load(project_id, route.profile_id)
            saved = route
            async with route_files(point.project):
                await self._migrate(point, route, at)
                loaded = await self._s.facts.load(point, route)
                stopped = await self._stop_if_changed(point, route, loaded, at)
                if stopped is not None:
                    # Остановка записана (таблица 5.5), пропуск отклонён после записи.
                    saved = stopped
                    refusal = _stopped(stopped.status.value)
                else:
                    skipped = skip(route, loaded.facts, participant_id, by=actor_id, at=at)
                    settled = await self._settle(point, skipped, at, loaded)
            if refusal is None:
                saved = await self._commit(
                    settled,
                    [
                        _event(skipped, participant_id, at, actor_id),
                        *frozen_events(settled, at),
                        *closing_events(settled, at),
                    ],
                    actor_id=actor_id,
                    at=at,
                    extra=[Notify(Notice.skipped, (participant_id,))],
                )
        if refusal is not None:
            raise refusal
        return await self._details(actor, point, saved)


def _stopped(status: str) -> RouteConflictError:
    return RouteConflictError(
        "invalid_transition",
        localized_error(
            f"Маршрут остановлен («{status}»): пропустить участника нельзя",
            f"The route has been stopped (“{status}”): the participant cannot be skipped",
        ),
    )


def _event(route: SigningRoute, participant_id: UUID, at: datetime, actor_id: UUID) -> RouteEvent:
    """Событие `skipped`: пропущенные пары, документы с оставленной меткой и перефиксированные без неё (13.8)."""
    mark = route.participant(participant_id).skipped
    assert mark is not None  # noqa: S101 — `skip` всегда записывает пропуск
    return RouteEvent(
        route.id,
        route.round,
        at,
        EventKind.skipped,
        actor_id,
        participant_id=participant_id,
        details={
            "slots": [{"doc_id": pair.doc_id, "slot_id": pair.slot_id} for pair in mark.pairs],
            "kept_marks": list(mark.kept_marks),
            "refrozen": list(mark.refrozen),
        },
    )
