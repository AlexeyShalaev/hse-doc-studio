"""Места подписей из пака по документам и их происхождение (docs/design/signing-route.md, 15.3, 15.4 и 15.10).

Пак задаёт место слота на документе: запись `placements` документа, иначе общее `default_placement`
(`SignatureSlotDef.place_for`), и метки даты документа (`default_dates`, `SignatureSlotDef.dates_for`).

Размещение в состоянии подписей бывает трёх видов (`PlacementOrigin`):

- `pack`: место поставил пресет (`from_pack`), и отпечаток текущего места и меток даты совпадает с записанным;
- `seed`: затравка без пометки, которую Студия создала из пака (загрузка картинки ставит выключенные места на всех
  документах слота): `from_pack` нет, место выключено, совпадает с местом из пака этой или более ранней версии
  шаблона до 0,1 мм, меток даты и даты в рамке нет;
- `manual`: всё остальное, место поставил или изменил автор.

Модуль чистый: версии шаблона ему передают, сам он их не ищет.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import replace
from typing import Protocol

from hse_doc_studio.core.catalog import SignatureDefaultPlacement, SignatureSlotDef
from hse_doc_studio.core.enums import DateMarkAlign, DateMarkFormat, PlacementOrigin
from hse_doc_studio.core.value_objects import DateMark, FromPack, SignaturePlacement

# Точность сравнения мест и отпечатка: 0,1 мм. Сравнение с допуском половины шага, чтобы 80.04 и 80.0 совпадали.
_DECIMALS = 1
_TOLERANCE_MM = 0.05 + 1e-9
DIGEST_LENGTH = 16


class _Mark(Protocol):
    """Метка даты для отпечатка: метка размещения (`DateMark`) или метка пака (`SignatureDefaultDate`)."""

    @property
    def page(self) -> int: ...
    @property
    def x_mm(self) -> float: ...
    @property
    def y_mm(self) -> float: ...
    @property
    def width_mm(self) -> float: ...
    @property
    def height_mm(self) -> float: ...
    @property
    def format(self) -> DateMarkFormat: ...
    @property
    def align(self) -> DateMarkAlign: ...


def _mm(value: float) -> float:
    # `+ 0.0` превращает -0.0 в 0.0: иначе отпечаток зависел бы от знака нуля.
    return round(float(value), _DECIMALS) + 0.0


def place_digest(page: int, x_mm: float, y_mm: float, width_mm: float, dates: Iterable[_Mark]) -> str:
    """Отпечаток места и меток даты: sha256 (первые 16 знаков) канонического JSON, мм округлены до 0,1.

    `id` меток не входит (у пака их нет), порядок меток не важен: метки сортируются. `enabled`, дата в рамке и момент
    подписи не входят: это не форма места, их меняет маршрут и автор, не трогая геометрию.
    """
    marks = sorted(
        (
            {
                "page": int(mark.page),
                "x_mm": _mm(mark.x_mm),
                "y_mm": _mm(mark.y_mm),
                "width_mm": _mm(mark.width_mm),
                "height_mm": _mm(mark.height_mm),
                "format": DateMarkFormat(mark.format).value,
                "align": DateMarkAlign(mark.align).value,
            }
            for mark in dates
        ),
        key=lambda item: json.dumps(item, sort_keys=True),
    )
    payload = {"page": int(page), "x_mm": _mm(x_mm), "y_mm": _mm(y_mm), "width_mm": _mm(width_mm), "dates": marks}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def placement_digest(placement: SignaturePlacement) -> str:
    """Отпечаток текущего места и меток даты размещения."""
    return place_digest(placement.page, placement.x_mm, placement.y_mm, placement.width_mm, placement.dates)


def pack_digest(slot_def: SignatureSlotDef, doc_def_id: str) -> str:
    """Отпечаток места и меток даты, которые пак задаёт слоту на документе."""
    place = slot_def.place_for(doc_def_id)
    return place_digest(place.page, place.x_mm, place.y_mm, place.width_mm, slot_def.dates_for(doc_def_id))


def same_place(placement: SignaturePlacement, place: SignatureDefaultPlacement) -> bool:
    """Место размещения совпадает с местом из пака: та же страница, координаты и ширина до 0,1 мм."""
    return placement.page == place.page and all(
        abs(a - b) <= _TOLERANCE_MM
        for a, b in (
            (placement.x_mm, place.x_mm),
            (placement.y_mm, place.y_mm),
            (placement.width_mm, place.width_mm),
        )
    )


def seed_places(slot_defs: Iterable[SignatureSlotDef], doc_def_id: str) -> tuple[SignatureDefaultPlacement, ...]:
    """Места, по которым узнаётся затравка: место документа и общее место слота в каждой переданной версии.

    `slot_defs` один слот каталога в версии проекта и во всех выпущенных более ранних версиях того же шаблона
    (15.10): patch-версия с новыми местами не превращает затравки прежних версий в ручные места.
    """
    places: list[SignatureDefaultPlacement] = []
    for slot_def in slot_defs:
        for place in (slot_def.place_for(doc_def_id), slot_def.default_placement):
            if place not in places:
                places.append(place)
    return tuple(places)


def is_from_pack(placement: SignaturePlacement) -> bool:
    """Место поставил пресет и с тех пор его геометрию и метки даты не меняли."""
    return placement.from_pack is not None and placement.from_pack.digest == placement_digest(placement)


def is_seed(placement: SignaturePlacement, seeds: Iterable[SignatureDefaultPlacement]) -> bool:
    """Затравка без пометки: выключенное место из пака без меток и даты, которое никто не трогал."""
    if placement.from_pack is not None or placement.enabled or placement.dates or placement.sign_date:
        return False
    return any(same_place(placement, place) for place in seeds)


def placement_origin(placement: SignaturePlacement, seeds: Iterable[SignatureDefaultPlacement]) -> PlacementOrigin:
    """Вид размещения: место из шаблона, затравка или ручное (см. модуль)."""
    if is_from_pack(placement):
        return PlacementOrigin.pack
    if is_seed(placement, seeds):
        return PlacementOrigin.seed
    return PlacementOrigin.manual


def stamp_from_pack(placement: SignaturePlacement, version: str) -> SignaturePlacement:
    """Пометить размещение местом из шаблона версии `version` с отпечатком его текущего места и меток."""
    return replace(placement, from_pack=FromPack(version=version, digest=placement_digest(placement)))


def keep_from_pack(before: SignaturePlacement, after: SignaturePlacement) -> SignaturePlacement:
    """Системная правка места (расширение под плашку ЭП) не делает место из шаблона ручным.

    Если до правки место было как в шаблоне, пометка переписывается под новую геометрию с той же версией; иначе
    размещение остаётся как есть (ручное место остаётся ручным, пометки нет).
    """
    if before.from_pack is None or not is_from_pack(before):
        return after
    return stamp_from_pack(after, before.from_pack.version)


def clear_from_pack(placement: SignaturePlacement) -> SignaturePlacement:
    """Правка человеком снимает пометку «место из шаблона» (15.4)."""
    return placement if placement.from_pack is None else replace(placement, from_pack=None)


def pack_marks(slot_def: SignatureSlotDef, doc_def_id: str) -> tuple[DateMark, ...]:
    """Метки даты пака для документа как метки размещения: у пака их id нет, сервер назначает `d1`, `d2`, ..."""
    return tuple(
        DateMark(
            id=f"d{number}",
            page=mark.page,
            x_mm=mark.x_mm,
            y_mm=mark.y_mm,
            width_mm=mark.width_mm,
            height_mm=mark.height_mm,
            format=mark.format,
            align=mark.align,
        )
        for number, mark in enumerate(slot_def.dates_for(doc_def_id), start=1)
    )


def pack_placement(
    slot_def: SignatureSlotDef, doc_def_id: str, base: SignaturePlacement | None, version: str
) -> SignaturePlacement:
    """Место и метки даты слота на документе как в шаблоне версии `version`, с пометкой `from_pack` (15.5, 15.6).

    Включённость, дата в рамке и момент подписи берутся у `base` (без него место выключено): их не задаёт пак и не
    учитывает отпечаток. Включает место тот, кто применяет пресет, а «Вернуть место из шаблона» её не меняет.
    """
    place = slot_def.place_for(doc_def_id)
    start = base or SignaturePlacement(
        enabled=False, page=place.page, x_mm=place.x_mm, y_mm=place.y_mm, width_mm=place.width_mm
    )
    placement = replace(
        start,
        page=place.page,
        x_mm=place.x_mm,
        y_mm=place.y_mm,
        width_mm=place.width_mm,
        dates=pack_marks(slot_def, doc_def_id),
    )
    return stamp_from_pack(placement, version)
