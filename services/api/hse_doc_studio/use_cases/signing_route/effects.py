"""Файловые эффекты расчёта маршрута (docs/design/signing-route.md, разделы 4.2, 6.1 и 6.2).

Придержать и открыть картинку слота, заполнить плашку данными ключа участника, зафиксировать документ. Вызывающий
держит `project_lock` проекта и после эффектов перечитывает факты и обновляет снимок (`refresh_snapshot`).
Уведомления (`Notify`) здесь не выполняются: их рассылает сценарий в своей транзакции.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from hse_doc_studio.core.repositories import ISignatureRepository
from hse_doc_studio.core.signatures.plan import VisibleMark, mark_of
from hse_doc_studio.core.signing_route.effects import Effect, FillPlate, Freeze, Release, Withhold
from hse_doc_studio.core.signing_route.entities import SigningRoute
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.signatures.freeze_pdf import FreezePdfInput, FreezePdfUC
from hse_doc_studio.use_cases.signing_route.point import RoutePoint


def _now() -> datetime:
    return datetime.now(UTC)


class RouteFileEffects:
    def __init__(self, signature_repo: ISignatureRepository, freeze_uc: FreezePdfUC) -> None:
        self._signatures = signature_repo
        self._freeze = freeze_uc

    async def apply(
        self, point: RoutePoint, route: SigningRoute, effects: Sequence[Effect], *, at: datetime | None = None
    ) -> tuple[str, ...]:
        """Выполнить эффекты по порядку расчёта; возвращает зафиксированные документы."""
        folder = point.project.folder
        moment = at or _now()
        state = self._signatures.get_state(folder)
        frozen: list[str] = []
        for effect in effects:
            if isinstance(effect, Freeze):
                self._save(folder, state, _date_plates(state, effect.doc_id, moment))
                await self._freeze.execute(FreezePdfInput(project_id=point.project_id, doc_id=effect.doc_id))
                state = self._signatures.get_state(folder)
                frozen.append(effect.doc_id)
            else:
                state = self._save(folder, state, _apply(state, route, effect))
        return tuple(frozen)

    def _save(self, folder: Path, before: SignaturesState, after: SignaturesState) -> SignaturesState:
        if after != before:
            self._signatures.save_state(folder, after)
        return after


def _apply(state: SignaturesState, route: SigningRoute, effect: Effect) -> SignaturesState:
    if isinstance(effect, Withhold):
        return _withheld(state, effect.doc_id, effect.slot_id, held=True)
    if isinstance(effect, Release):
        released = _withheld(state, effect.doc_id, effect.slot_id, held=False)
        approval = route.participant(effect.participant_id).approval
        return _set_date(released, effect.doc_id, effect.slot_id, approval.at if approval is not None else None)
    if isinstance(effect, FillPlate):
        slot = state.slots.get(effect.slot_id)
        if slot is None or slot.signer is not None:
            return state
        return replace(state, slots={**state.slots, effect.slot_id: replace(slot, signer=effect.signer)})
    return state


def _withheld(state: SignaturesState, doc_id: str, slot_id: str, *, held: bool) -> SignaturesState:
    current = state.withheld.get(doc_id, frozenset())
    updated = current | {slot_id} if held else current - {slot_id}
    if updated == current:
        return state
    withheld = {k: v for k, v in state.withheld.items() if k != doc_id}
    if updated:
        withheld[doc_id] = frozenset(updated)
    return replace(state, withheld=withheld)


def _set_date(state: SignaturesState, doc_id: str, slot_id: str, at: datetime | None) -> SignaturesState:
    """Дата у размещения, где автор её включил: дата согласования картинки или фиксации плашки (раздел 6.2)."""
    placement = state.placements.get(doc_id, {}).get(slot_id)
    if placement is None or placement.sign_date is None or at is None:
        return state
    date = at.astimezone(UTC).date().isoformat()
    if placement.sign_date == date:
        return state
    doc_placements = {**state.placements[doc_id], slot_id: replace(placement, sign_date=date)}
    return replace(state, placements={**state.placements, doc_id: doc_placements})


def _date_plates(state: SignaturesState, doc_id: str, at: datetime) -> SignaturesState:
    for slot_id in state.placements.get(doc_id, {}):
        if mark_of(state.slots.get(slot_id)) is VisibleMark.plate:
            state = _set_date(state, doc_id, slot_id, at)
    return state
