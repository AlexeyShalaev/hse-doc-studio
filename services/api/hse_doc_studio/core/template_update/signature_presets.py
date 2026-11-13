"""Места подписей из шаблона при обновлении проекта на новую версию (docs/design/signing-route.md, 15.9 и 15.10).

Пресет мест читается вживую из версии проекта, но то, что уже записано в `signatures.json`, само не меняется. Пункт
плана `signature_presets` переводит на новую версию места, которые «как в шаблоне» (`from_pack` с совпавшим
отпечатком) или затравки без пометки: место и метки даты слота документа берутся из новой версии
(`SignatureSlotDef.place_for`, `dates_for`), пометка `from_pack` ставится с новой версией, `enabled`, дата в рамке и
момент подписи сохраняются. Не трогаются:

- ручные места (`manual`);
- документы, которые держит маршрут подписания (`route`): правка мест остановила бы его, а обновление шаблона не
  действие маршрута;
- документы с ЭП над зафиксированным PDF (`signed`): новое место устарило бы фиксацию и сбросило бы подписи.

Отмена обновления возвращает места, которые после него никто не трогал (`revert_places`): сравнение идёт по JSON
`signatures.json` трёх моментов (до обновления, сразу после, сейчас), так незнакомые этой Студии поля переживают
отмену.

Модуль чистый: происхождение мест, версии шаблона и документы маршрутов ему передают.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from hse_doc_studio.core.catalog import SignatureSlotDef
from hse_doc_studio.core.signatures.pack_places import stamp_from_pack
from hse_doc_studio.core.signatures.stamps import widen_for_plate
from hse_doc_studio.core.value_objects import DateMark, SignaturePlacement, SignaturesState

SIGNATURES_PATH = ".hse-studio/signatures.json"

# Поля размещения в `signatures.json`, которые меняет обновление: место, метки даты и пометка. Остальные (`enabled`,
# дата в рамке, момент подписи) обновление сохраняет, поэтому и отмена их не трогает.
_SHAPE_KEYS = ("page", "x_mm", "y_mm", "width_mm", "dates", "from_pack")


class PresetKeptReason(StrEnum):
    """Почему место подписи из шаблона не обновится (15.9)."""

    manual = "manual"  # место изменено автором
    route = "route"  # документ держит маршрут подписания
    signed = "signed"  # над зафиксированным PDF документа есть ЭП


@dataclass(frozen=True)
class PresetPlace:
    doc_id: str
    slot_id: str


@dataclass(frozen=True)
class PresetKept:
    doc_id: str
    slot_id: str
    reason: PresetKeptReason


@dataclass(frozen=True)
class SignaturePresetsPlan:
    """Пункт плана обновления `signature_presets`: какие места переходят на новую версию, какие остаются.

    `placements` новые размещения пар `updated` в том же порядке: применение пишет ровно их.
    """

    updated: tuple[PresetPlace, ...] = ()
    kept: tuple[PresetKept, ...] = ()
    placements: tuple[SignaturePlacement, ...] = field(default=(), compare=False)

    @property
    def is_empty(self) -> bool:
        return not self.updated and not self.kept

    def fingerprint_lines(self) -> tuple[str, ...]:
        """Строки для отпечатка плана: применение с другим составом мест было бы не тем, что видел человек."""
        lines = [f"signature_presets:updated:{p.doc_id}:{p.slot_id}" for p in self.updated]
        lines += [f"signature_presets:kept:{k.doc_id}:{k.slot_id}:{k.reason.value}" for k in self.kept]
        return tuple(lines)

    def apply(self, state: SignaturesState) -> SignaturesState:
        """Состояние подписей с местами `updated` из новой версии; без мест состояние возвращается как есть."""
        if not self.updated:
            return state
        placements = {doc_id: dict(slot_map) for doc_id, slot_map in state.placements.items()}
        for place, placement in zip(self.updated, self.placements, strict=True):
            placements.setdefault(place.doc_id, {})[place.slot_id] = placement
        return replace(state, placements=placements)


def pack_place(
    placement: SignaturePlacement, slot_def: SignatureSlotDef, doc_def_id: str, version: str
) -> SignaturePlacement:
    """Размещение на месте слота документа из пака версии `version` с её метками даты и пометкой `from_pack`.

    `enabled`, дата в рамке и момент подписи остаются от `placement`. Метки получают id `d1`, `d2`, ... по порядку пака.
    """
    place = slot_def.place_for(doc_def_id)
    marks = tuple(
        DateMark(
            id=f"d{n}",
            page=mark.page,
            x_mm=mark.x_mm,
            y_mm=mark.y_mm,
            width_mm=mark.width_mm,
            height_mm=mark.height_mm,
            format=mark.format,
            align=mark.align,
        )
        for n, mark in enumerate(slot_def.dates_for(doc_def_id), start=1)
    )
    moved = replace(placement, page=place.page, x_mm=place.x_mm, y_mm=place.y_mm, width_mm=place.width_mm, dates=marks)
    return stamp_from_pack(moved, version)


def widened(state: SignaturesState, doc_id: str, slot_id: str, placement: SignaturePlacement) -> SignaturePlacement:
    """Место после расширения под плашку открепленной ЭП, как его расширила бы Студия (`widen_for_plate`, 6.3).

    Пометка `from_pack` переписывается под широкую рамку (`keep_from_pack`): место остаётся местом из шаблона.
    """
    single = replace(state, placements={doc_id: {slot_id: placement}})
    return widen_for_plate(single, [(doc_id, slot_id)]).placements[doc_id][slot_id]


def signed_docs(state: SignaturesState) -> frozenset[str]:
    """Документы, над зафиксированным PDF которых есть ЭП: открепленная или встроенная."""
    return frozenset(doc_id for doc_id in state.frozen if state.detached.get(doc_id) or state.embedded.get(doc_id))


def kept_reason(
    doc_id: str, *, manual: bool, held_docs: AbstractSet[str], signed: AbstractSet[str]
) -> PresetKeptReason | None:
    """Почему место не обновится; None, если обновится. Маршрут важнее всего: документ под ним не трогают совсем."""
    if doc_id in held_docs:
        return PresetKeptReason.route
    if doc_id in signed:
        return PresetKeptReason.signed
    if manual:
        return PresetKeptReason.manual
    return None


def _signed_json(data: Mapping[str, Any]) -> set[str]:
    frozen = data.get("frozen") or {}
    detached = data.get("detached") or {}
    embedded = data.get("embedded") or {}
    return {doc_id for doc_id in frozen if detached.get(doc_id) or embedded.get(doc_id)}


def _shape(placement: Mapping[str, Any] | None) -> tuple[Any, ...] | None:
    if not isinstance(placement, Mapping):
        return None
    return tuple(placement.get(key) for key in _SHAPE_KEYS)


def revert_places(
    before: Mapping[str, Any], after: Mapping[str, Any], current: Mapping[str, Any], held_docs: Iterable[str] = ()
) -> tuple[dict[str, Any] | None, tuple[PresetPlace, ...]]:
    """Отмена перевода мест: JSON `signatures.json` после отмены и вернувшиеся места; None, если возвращать нечего.

    `before` до обновления, `after` сразу после него, `current` сейчас. Место возвращается, если обновление его
    меняло, а после обновления никто не трогал (место, метки и пометка как сразу после обновления). Документы под
    маршрутом (`held_docs`) и с ЭП над зафиксированным PDF не трогаются, как и при обновлении. `enabled`, дата в рамке
    и момент подписи остаются текущими.
    """
    skip = set(held_docs) | _signed_json(current)
    before_places = before.get("placements") or {}
    after_places = after.get("placements") or {}
    current_places = current.get("placements") or {}
    restored: list[PresetPlace] = []
    result = json.loads(json.dumps(dict(current)))
    for doc_id, slot_map in sorted(after_places.items()):
        if doc_id in skip or not isinstance(slot_map, Mapping):
            continue
        for slot_id, placement in sorted(slot_map.items()):
            prior = (before_places.get(doc_id) or {}).get(slot_id)
            now = (current_places.get(doc_id) or {}).get(slot_id)
            if not isinstance(prior, Mapping):
                continue
            was, became, is_now = _shape(prior), _shape(placement), _shape(now)
            if is_now is None or was == became or is_now != became:
                continue
            target = result["placements"][doc_id][slot_id]
            for key in _SHAPE_KEYS:
                target[key] = prior.get(key)
            restored.append(PresetPlace(doc_id, slot_id))
    return (result if restored else None), tuple(restored)
