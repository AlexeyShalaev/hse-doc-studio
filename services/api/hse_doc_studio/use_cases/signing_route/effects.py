"""Файловые эффекты расчёта маршрута (docs/design/signing-route.md, разделы 4.2, 6.1 и 6.2).

Придержать и открыть картинку слота, записать момент подписи у меток даты, заполнить плашку данными ключа участника,
зафиксировать документ. Вызывающий
держит `project_lock` проекта и после эффектов перечитывает факты и обновляет снимок (`refresh_snapshot`).
Уведомления (`Notify`) здесь не выполняются: их рассылает сценарий в своей транзакции.

Плашка, заполненная открытым ключом OpenPGP из профиля подписанта, кладёт этот ключ в связку ключей: иначе
открепленную подпись `.asc`, которую подписант загрузит после фиксации, нечем было бы проверить (`unknown_key`).
Сертификату X.509 это не нужно: он приходит внутри самой подписи.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import structlog

from hse_doc_studio.core.enums import SignedAtSource
from hse_doc_studio.core.repositories import ISignatureRepository
from hse_doc_studio.core.signatures.dates import to_display
from hse_doc_studio.core.signatures.errors import GpgError, GpgUnavailableError
from hse_doc_studio.core.signatures.plan import VisibleMark, mark_of
from hse_doc_studio.core.signatures.ports import IOpenPgpKeyImporter
from hse_doc_studio.core.signatures.signer_profile import ISignerProfileRepository, PublicKeyKind
from hse_doc_studio.core.signing_route.audit import signing_route_scope
from hse_doc_studio.core.signing_route.effects import (
    Effect,
    FillPlate,
    Freeze,
    RecordSignedAt,
    Release,
    Skip,
    Unskip,
    Withhold,
)
from hse_doc_studio.core.signing_route.entities import DocSlot, SigningRoute
from hse_doc_studio.core.value_objects import SignaturesState, SignedAt, SkippedSlot
from hse_doc_studio.use_cases.signatures.freeze_pdf import FreezePdfInput, FreezePdfUC
from hse_doc_studio.use_cases.signing_route.point import RoutePoint

logger = structlog.get_logger()


def _now() -> datetime:
    return datetime.now(UTC)


class RouteFileEffects:
    def __init__(
        self,
        signature_repo: ISignatureRepository,
        freeze_uc: FreezePdfUC,
        profiles: ISignerProfileRepository | None = None,
        key_importer: IOpenPgpKeyImporter | None = None,
    ) -> None:
        self._signatures = signature_repo
        self._freeze = freeze_uc
        self._profiles = profiles
        self._key_importer = key_importer

    @property
    def signatures(self) -> ISignatureRepository:
        """Состояние подписей проекта: им же пишет версию на подписи сценарий отправки (`RoutePinning`)."""
        return self._signatures

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
                # Фиксацию делает маршрут: запись `signature.freeze` журнала аудита получает его `route_id`.
                with signing_route_scope(route.id):
                    await self._freeze.execute(FreezePdfInput(project_id=point.project_id, doc_id=effect.doc_id))
                state = self._signatures.get_state(folder)
                frozen.append(effect.doc_id)
            else:
                changed = _apply(state, route, effect)
                if isinstance(effect, FillPlate) and changed != state:
                    await self._import_profile_key(route, effect)
                state = self._save(folder, state, changed)
        return tuple(frozen)

    async def _import_profile_key(self, route: SigningRoute, effect: FillPlate) -> None:
        """Открытый ключ OpenPGP из профиля участника в связку, если плашка заполнена именно им."""
        if self._profiles is None or self._key_importer is None or effect.signer.kind != PublicKeyKind.openpgp.value:
            return
        user_id = route.participant(effect.participant_id).user_id
        if user_id is None:
            return
        key = (await self._profiles.get(user_id.hex)).public_key
        if key is None or key.kind is not PublicKeyKind.openpgp or key.plate.signer_id != effect.signer.signer_id:
            return
        try:
            await asyncio.to_thread(self._key_importer.import_public_key, key.data)
        except (GpgUnavailableError, GpgError) as exc:
            # Плашка всё равно заполнена: подпись без ключа в связке получит вердикт «ключ неизвестен», и план
            # попросит загрузить открытый ключ.
            logger.warning("signing route: profile key not imported", route_id=str(route.id), error=str(exc))

    def _save(self, folder: Path, before: SignaturesState, after: SignaturesState) -> SignaturesState:
        if after != before:
            self._signatures.save_state(folder, after)
        return after


def _apply(state: SignaturesState, route: SigningRoute, effect: Effect) -> SignaturesState:
    if isinstance(effect, Skip):
        return _skipped(state, route, effect)
    if isinstance(effect, Unskip):
        return _unskipped(state, effect.doc_id, effect.slot_id)
    if isinstance(effect, RecordSignedAt):
        return record_signed_at(state, effect)
    return _apply_marks(state, route, effect)


def record_signed_at(state: SignaturesState, effect: RecordSignedAt) -> SignaturesState:
    """Момент согласия у размещения с метками даты (14.4): ISO с поясом UTC и отпечаток согласия документа."""
    placement = state.placements.get(effect.doc_id, {}).get(effect.slot_id)
    if placement is None:
        return state
    signed_at = SignedAt(
        at=effect.at.astimezone(UTC).isoformat(timespec="seconds"), source=SignedAtSource.approval, token=effect.token
    )
    if placement.signed_at == signed_at:
        return state
    doc_placements = {**state.placements[effect.doc_id], effect.slot_id: replace(placement, signed_at=signed_at)}
    return replace(state, placements={**state.placements, effect.doc_id: doc_placements})


def _apply_marks(state: SignaturesState, route: SigningRoute, effect: Effect) -> SignaturesState:
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


def _skipped(state: SignaturesState, route: SigningRoute, effect: Skip) -> SignaturesState:
    """Пропуск пары в состоянии подписей (13.3): раунд и время берутся у участника, чей это пропуск."""
    pair = DocSlot(effect.doc_id, effect.slot_id)
    skip = next((p.skipped for p in route.participants if p.skipped is not None and pair in p.skipped.pairs), None)
    if skip is None:
        return state
    record = SkippedSlot(
        profile_id=route.profile_id,
        route_id=str(route.id),
        round=skip.round,
        at=skip.at.astimezone(UTC).isoformat(timespec="seconds"),
        keep_mark=effect.keep_mark,
    )
    if state.skipped.get(effect.doc_id, {}).get(effect.slot_id) == record:
        return state
    doc_skips = {**state.skipped.get(effect.doc_id, {}), effect.slot_id: record}
    return replace(state, skipped={**state.skipped, effect.doc_id: doc_skips})


def _unskipped(state: SignaturesState, doc_id: str, slot_id: str) -> SignaturesState:
    doc_skips = state.skipped.get(doc_id, {})
    if slot_id not in doc_skips:
        return state
    rest = {k: v for k, v in doc_skips.items() if k != slot_id}
    skipped = {k: v for k, v in state.skipped.items() if k != doc_id}
    if rest:
        skipped[doc_id] = rest
    return replace(state, skipped=skipped)


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
    """Дата у размещения, где автор её включил: дата согласования картинки или фиксации плашки (раздел 6.2).

    День по Москве, как у меток даты (14.4): согласие в 01:30 по Москве это уже этот день, а не предыдущий по UTC.
    """
    placement = state.placements.get(doc_id, {}).get(slot_id)
    if placement is None or placement.sign_date is None or at is None:
        return state
    date = to_display(at).date().isoformat()
    if placement.sign_date == date:
        return state
    doc_placements = {**state.placements[doc_id], slot_id: replace(placement, sign_date=date)}
    return replace(state, placements={**state.placements, doc_id: doc_placements})


def _date_plates(state: SignaturesState, doc_id: str, at: datetime) -> SignaturesState:
    for slot_id in state.placements.get(doc_id, {}):
        if mark_of(state.slots.get(slot_id)) is VisibleMark.plate:
            state = _set_date(state, doc_id, slot_id, at)
    return state
