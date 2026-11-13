"""Метки даты на документе под маршрутом: правка сценарием маршрута (docs/design/signing-route.md, 14.5 и 14.6).

Правка размещений документа идущего маршрута закрыта (`route_locked`), а правка у завершённого остановила бы его
(`marks_changed`). Метки даты нужно уметь добавить на живом маршруте, поэтому на документе, который держит маршрут
`active` или `completed`, их правит этот сценарий:

1. блокировка строки маршрута и `project_lock` с пометкой `route_files`, перенос маршрута 0.20.0, сверка;
2. если правка сбросит ЭП над зафиксированным PDF, а `confirm_reset` нет: 409 `resets_signatures`, ничего не записано;
3. запись меток, расчёт и эффекты (`_settle`): дата согласия у уже согласовавших (`RecordSignedAt`), перефиксация в
   фазе `signing`, снимок принимает правку;
4. владельцы сброшенных ЭП снова в `to_sign`, завершённый маршрут снова `active`, запрос «Подпишите итоговый PDF»
   приходит им заново (`resign_requests`, ключ повтора с отпечатком нового B);
5. событие `marks_edited` и его запись в журнале аудита (`signing_route.marks_edit`).

Права: правку размещения проверяет ручка (`FILES_WRITE`); на документе под маршрутом нужно ещё право отправки
маршрута (`SUBMISSION_CREATE`), без него 409 `route_locked`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.signatures.plan import frozen_is_current
from hse_doc_studio.core.signing_route.effects import RecordSignedAt
from hse_doc_studio.core.signing_route.engine import evaluate
from hse_doc_studio.core.signing_route.entities import (
    WATCHING_STATUSES,
    DocSlot,
    EventKind,
    ResetSignature,
    ResetsSignaturesError,
    RouteEvent,
    SigningRoute,
    date_from_route,
    route_locked,
)
from hse_doc_studio.core.signing_route.ports import DatesWrite
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.signing_route.effects import record_signed_at
from hse_doc_studio.use_cases.signing_route.facts import LoadedFacts
from hse_doc_studio.use_cases.signing_route.point import RoutePoint
from hse_doc_studio.use_cases.signing_route.scenario import (
    RouteScenario,
    Settled,
    closing_events,
    current_actor_uuid,
    frozen_events,
    route_files,
)


class RouteDatesEditing(RouteScenario):
    """`ISigningRouteGate.edit_dates` сервера."""

    async def edit_dates(
        self, project_id: UUID, doc_id: str, slot_id: str, write: DatesWrite, *, manual: bool, confirm_reset: bool
    ) -> SignaturesState | None:
        route = await self._s.routes.holding(project_id, doc_id)
        if route is None:
            return None
        pair = DocSlot(doc_id, slot_id)
        if route.status in WATCHING_STATUSES and await self._holds(route):
            if not await self._manages(project_id):
                raise route_locked()
            if manual and pair in route.pairs:
                raise date_from_route()
            return await self._edit(project_id, route.id, pair, write, confirm_reset=confirm_reset)
        if manual and pair in route.pairs:
            raise date_from_route()
        return None

    async def _holds(self, route: SigningRoute) -> bool:
        """Маршрут по расчёту идёт или завершён: держит правку меток. Точку не прочитать (проект или пак сняты):
        маршрут считается держащим, как по хранимому статусу."""
        try:
            point = await self._s.points.load(route.project_id, route.profile_id)
        except NotFoundError:
            return True
        loaded = await self._s.facts.load(point, route)
        return evaluate(route, loaded.facts).status in WATCHING_STATUSES

    async def _edit(
        self, project_id: UUID, route_id: UUID, pair: DocSlot, write: DatesWrite, *, confirm_reset: bool
    ) -> SignaturesState | None:
        """Правка под блокировками; None, если маршрут тем временем перестал держать документ (остановлен,
        остановку записала сверка этого же сценария): тогда метки пишет вызывающий, как без маршрута."""
        actor_id = current_actor_uuid()
        at = self._s.clock()
        settled: Settled | None = None
        result: SignaturesState | None = None
        async with self._s.uow.begin():
            route = await self._get(project_id, route_id, lock=True)
            if route.status not in WATCHING_STATUSES:
                return None
            point = await self._s.points.load(project_id, route.profile_id)
            async with route_files(point.project):
                await self._migrate(point, route, at)
                loaded = await self._s.facts.load(point, route)
                if await self._stop_if_changed(point, route, loaded, at) is not None:
                    return None
                edited = await write(loaded.state)
                if edited == loaded.state:
                    return edited
                resets = await self._resets(point, route, loaded, edited, pair)
                if resets and not confirm_reset:
                    raise ResetsSignaturesError(resets)
                self._s.effects.signatures.save_state(point.project.folder, edited)
                settled = await self._settle(point, route, at)
                result = settled.loaded.state
            assert settled is not None  # noqa: S101 — до записи без расчёта сценарий вышел выше
            await self._commit(
                settled,
                [
                    _event(route, pair, edited, settled, at, actor_id),
                    *frozen_events(settled, at),
                    *closing_events(settled, at),
                ],
                actor_id=actor_id,
                at=at,
            )
        return result

    async def _resets(
        self, point: RoutePoint, route: SigningRoute, loaded: LoadedFacts, edited: SignaturesState, pair: DocSlot
    ) -> tuple[ResetSignature, ...]:
        """ЭП над зафиксированным PDF, которые правка сбросит (14.5).

        Документ, чей B сейчас действителен, перефиксируют, если правка меняет его видимый слой: метки с датой, в
        том числе дозаполненной из согласия (`RecordSignedAt`), или ручная дата. А если владелец пары ещё не
        согласовал и от меток даты впервые стал менять видимый слой (14.4), B перефиксируют после его согласия:
        эти подписи тоже сбрасываются, предупреждаем сейчас.
        """
        after = await self._s.facts.load(point, route, edited)
        records = [e for e in evaluate(route, after.facts).effects if isinstance(e, RecordSignedAt)]
        if records:
            simulated = edited
            for record in records:
                simulated = record_signed_at(simulated, record)
            after = await self._s.facts.load(point, route, simulated)
        owner = next((p for p in route.participants if pair in p.assignments), None)
        becomes_changer = (
            owner is not None
            and evaluate(route, after.facts).participant(owner.id).changes_visible
            and not evaluate(route, loaded.facts).participant(owner.id).changes_visible
        )
        state = loaded.state
        found: list[DocSlot] = []
        for doc_id in route.docs:
            frozen = state.frozen.get(doc_id)
            signed = {*state.detached.get(doc_id, {}), *state.embedded.get(doc_id, {})}
            if frozen is None or not signed or frozen_is_current(frozen, loaded.facts.doc(doc_id)) is not None:
                continue
            redrawn = frozen_is_current(frozen, after.facts.doc(doc_id)) is not None
            if redrawn or (becomes_changer and doc_id == pair.doc_id):
                found += [DocSlot(doc_id, slot_id) for slot_id in sorted(signed)]
        return await self._named(route, state, found)

    async def _named(
        self, route: SigningRoute, state: SignaturesState, pairs: list[DocSlot]
    ) -> tuple[ResetSignature, ...]:
        """Имя подписанта: участник маршрута по аккаунту, иначе подписант из самой подписи, иначе слот."""
        owners = {pair: p for p in route.participants for pair in p.assignments}
        users = {p.user_id for pair in pairs if (p := owners.get(pair)) is not None and p.user_id is not None}
        names = await self._s.people.names(users) if users else {}
        resets: list[ResetSignature] = []
        for pair in pairs:
            owner = owners.get(pair)
            name = names.get(owner.user_id) if owner is not None and owner.user_id is not None else None
            detached = state.detached.get(pair.doc_id, {}).get(pair.slot_id)
            embedded = state.embedded.get(pair.doc_id, {}).get(pair.slot_id)
            signer = detached.signer if detached is not None else embedded.signer if embedded is not None else ""
            resets.append(ResetSignature(pair.doc_id, pair.slot_id, name or signer or pair.slot_id))
        return tuple(resets)


def _event(
    route: SigningRoute, pair: DocSlot, edited: SignaturesState, settled: Settled, at: datetime, actor_id: UUID | None
) -> RouteEvent:
    """Событие `marks_edited`: документ, слот, сколько у него меток даты и чьи ЭП сброшены перефиксацией (14.6)."""
    placement = edited.placements.get(pair.doc_id, {}).get(pair.slot_id)
    return RouteEvent(
        route.id,
        route.round,
        at,
        EventKind.marks_edited,
        actor_id,
        details={
            "doc_id": pair.doc_id,
            "slot_id": pair.slot_id,
            "marks": len(placement.dates) if placement is not None else 0,
            "reset": [{"doc_id": p.doc_id, "slot_id": p.slot_id} for p in settled.reset],
        },
    )
