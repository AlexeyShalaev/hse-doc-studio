"""Места подписей из пака по документам и их происхождение (docs/design/signing-route.md, 15.3, 15.4 и 15.10).

Пак задаёт место слота на документе: запись `placements` документа, иначе общее `default_placement`
(`SignatureSlotDef.place_for`), и метки даты документа (`default_dates`, `SignatureSlotDef.dates_for`).

Размещение в состоянии подписей бывает трёх видов (`PlacementOrigin`):

- `pack`: место поставил пресет (`from_pack`), и отпечаток текущего места и меток даты совпадает с записанным;
- `seed`: затравка без пометки, которую Студия создала из пака (загрузка картинки ставит выключенные места на всех
  документах слота): `from_pack` нет, место выключено, совпадает с местом из пака этой или более ранней версии
  шаблона до 0,1 мм, меток даты и даты в рамке нет;
- `manual`: всё остальное, место поставил или изменил автор.

Место пака бывает на якоре шаблона (15.17): тогда оно считается по линии собранного документа (`resolve_place`,
`anchor_box`), а якоря источника подписи документа ему передают (`SourceAnchors`). Якоря неизвестны: запасное место
пака в мм, если оно есть; свой загруженный PDF: места на якоре нет совсем.

Модуль чистый: версии шаблона и якоря ему передают, сам он их не ищет.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, Protocol

from hse_doc_studio.core.catalog import (
    ANCHOR_MIN_WIDTH_MM,
    AnchorDate,
    AnchorPlace,
    PackDate,
    PackPlace,
    SignatureDefaultDate,
    SignatureDefaultPlacement,
    SignatureSlotDef,
)
from hse_doc_studio.core.enums import AnchorState, DateMarkAlign, DateMarkFormat, PlacementOrigin, PlaceSource
from hse_doc_studio.core.signatures.anchors import BuildAnchor, BuildAnchors
from hse_doc_studio.core.signatures.dates import SHEET_HEIGHT_MM, SHEET_WIDTH_MM, frame_problem
from hse_doc_studio.core.value_objects import DateMark, FromPack, SignaturePlacement

# Точность сравнения мест и отпечатка: 0,1 мм. Сравнение с допуском половины шага, чтобы 80.04 и 80.0 совпадали.
_DECIMALS = 1
_TOLERANCE_MM = 0.05 + 1e-9
DIGEST_LENGTH = 16
# Верх рамки места не ниже этого (как у места пака в мм, 15.8): высота рамки зависит от картинки.
PLACE_MAX_Y_MM = 287.0


@dataclass(frozen=True)
class SourceAnchors:
    """Якоря источника подписи документа (15.17.4): None неизвестны; `own_pdf` источник это свой загруженный PDF,
    у которого строк шаблона нет (15.17.11)."""

    anchors: BuildAnchors | None = None
    own_pdf: bool = False

    @property
    def known(self) -> bool:
        return self.anchors is not None and not self.own_pdf

    def line(self, anchor_id: str) -> BuildAnchor | None:
        return self.anchors.get(anchor_id) if self.anchors is not None and not self.own_pdf else None


NO_ANCHORS = SourceAnchors()


@dataclass(frozen=True)
class AnchorRef:
    """Якорь места пака у пары и есть ли он в источнике подписи (`PlacementResponse.anchor`, 15.17.14)."""

    id: str
    state: AnchorState


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
    """Отпечаток записи места и меток даты, которые пак задаёт слоту на документе (R26 сравнивает версии).

    Запись в мм: отпечаток её места и меток, как у размещения. Запись на якоре (место или хоть одна метка, 15.17.10):
    отпечаток самой записи, `anchor`, `align`, сдвиги, ширина, запасное место и метки в канонической форме; переход
    пары с мм на якорь тоже изменение места.
    """
    entry = slot_def.entry_for(doc_def_id)
    marks = slot_def.dates_for(doc_def_id)
    if not slot_def.uses_anchors(doc_def_id):
        mm = slot_def.place_for(doc_def_id)
        return place_digest(mm.page, mm.x_mm, mm.y_mm, mm.width_mm, (m for m in marks if not isinstance(m, AnchorDate)))
    payload = {
        "place": _entry_json(entry),
        "dates": sorted((_mark_json(mark) for mark in marks), key=lambda item: json.dumps(item, sort_keys=True)),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]


def _mm_json(place: SignatureDefaultPlacement) -> dict[str, Any]:
    return {"page": int(place.page), "x_mm": _mm(place.x_mm), "y_mm": _mm(place.y_mm), "width_mm": _mm(place.width_mm)}


def _entry_json(entry: PackPlace) -> dict[str, Any]:
    if isinstance(entry, SignatureDefaultPlacement):
        return _mm_json(entry)
    return {
        "anchor": entry.anchor,
        "align": entry.align.value,
        "dx_mm": _mm(entry.dx_mm),
        "dy_mm": _mm(entry.dy_mm),
        "width_mm": None if entry.width_mm is None else _mm(entry.width_mm),
        "fallback": None if entry.fallback is None else _mm_json(entry.fallback),
    }


def _date_json(mark: SignatureDefaultDate) -> dict[str, Any]:
    return {
        "page": int(mark.page),
        "x_mm": _mm(mark.x_mm),
        "y_mm": _mm(mark.y_mm),
        "width_mm": _mm(mark.width_mm),
        "height_mm": _mm(mark.height_mm),
        "format": DateMarkFormat(mark.format).value,
        "align": DateMarkAlign(mark.align).value,
    }


def _mark_json(mark: PackDate) -> dict[str, Any]:
    if isinstance(mark, SignatureDefaultDate):
        return _date_json(mark)
    return {
        "anchor": mark.anchor,
        "format": mark.format.value,
        "height_mm": _mm(mark.height_mm),
        "width_mm": None if mark.width_mm is None else _mm(mark.width_mm),
        "dx_mm": _mm(mark.dx_mm),
        "dy_mm": None if mark.dy_mm is None else _mm(mark.dy_mm),
        "align": mark.align.value,
        "fallback": None if mark.fallback is None else _date_json(mark.fallback),
    }


# --- места на якорях (15.17.8) ---


def _aligned(align: DateMarkAlign, line: BuildAnchor, width: float) -> float:
    if align is DateMarkAlign.left:
        return line.x_mm
    if align is DateMarkAlign.right:
        return line.x_mm + line.width_mm - width
    return line.x_mm + (line.width_mm - width) / 2


def anchor_box(entry: AnchorPlace, line: BuildAnchor) -> SignatureDefaultPlacement | None:
    """Рамка подписи по линии якоря (15.17.8); None, если рамка за краем листа (`anchor_out_of_page`).

    Ширина рамки `width_mm` записи, иначе ширина линии, но не меньше 10 мм; `x` по `align` и `dx_mm`, верх рамки
    `y` линии плюс `dy_mm`. Округление до 0,1 мм, как у отпечатка места.
    """
    width = entry.width_mm if entry.width_mm is not None else max(ANCHOR_MIN_WIDTH_MM, line.width_mm)
    x = _mm(_aligned(entry.align, line, width) + entry.dx_mm)
    y = _mm(line.y_mm + entry.dy_mm)
    if x < 0 or x + width > SHEET_WIDTH_MM + 0.01 or not 0 <= y <= PLACE_MAX_Y_MM:
        return None
    return SignatureDefaultPlacement(page=line.page, x_mm=x, y_mm=y, width_mm=_mm(width))


def anchor_mark(entry: AnchorDate, line: BuildAnchor) -> SignatureDefaultDate | None:
    """Метка даты по линии якоря (15.17.7): ширина записи или линии, верх на `dy_mm` (по умолчанию рамка стоит на
    линии); None, если рамки нет (якорь-точка без ширины) или она за краем листа."""
    width = entry.width_mm if entry.width_mm is not None else line.width_mm
    dy = entry.dy_mm if entry.dy_mm is not None else -entry.height_mm
    x = _mm(_aligned(entry.align, line, width) + entry.dx_mm)
    y = _mm(line.y_mm + dy)
    if frame_problem(line.page, x, y, width, entry.height_mm, (SHEET_WIDTH_MM, SHEET_HEIGHT_MM)) is not None:
        return None
    return SignatureDefaultDate(
        page=line.page,
        x_mm=x,
        y_mm=y,
        width_mm=_mm(width),
        height_mm=_mm(entry.height_mm),
        format=entry.format,
        align=entry.align,
    )


def resolve_place(entry: PackPlace, src: SourceAnchors = NO_ANCHORS) -> SignatureDefaultPlacement | None:
    """Место записи пака на источнике подписи (15.17.8): запись в мм как есть; на якоре по линии сборки, если якоря
    известны (нет якоря или рамка за краем: места нет); якоря неизвестны: запасное место в мм или ничего; свой
    загруженный PDF: ничего, место ставит человек."""
    if isinstance(entry, SignatureDefaultPlacement):
        return entry
    if src.own_pdf:
        return None
    if src.anchors is None:
        return entry.fallback
    line = src.line(entry.anchor)
    return anchor_box(entry, line) if line is not None else None


def resolve_mark(entry: PackDate, src: SourceAnchors = NO_ANCHORS) -> SignatureDefaultDate | None:
    """Метка даты записи пака на источнике подписи, по тем же правилам, что `resolve_place`: метка, якоря которой
    в этой сборке нет, просто не ставится (русская и английская строка даты одной записью, 15.17.7)."""
    if isinstance(entry, SignatureDefaultDate):
        return entry
    if src.own_pdf:
        return None
    if src.anchors is None:
        return entry.fallback
    line = src.line(entry.anchor)
    return anchor_mark(entry, line) if line is not None else None


def anchor_ref(slot_def: SignatureSlotDef, doc_def_id: str, src: SourceAnchors) -> AnchorRef | None:
    """Якорь места пака у пары и есть ли он в источнике; None у места в мм."""
    entry = slot_def.entry_for(doc_def_id)
    if not isinstance(entry, AnchorPlace):
        return None
    if not src.known:
        return AnchorRef(entry.anchor, AnchorState.unknown)
    found = src.line(entry.anchor) is not None
    return AnchorRef(entry.anchor, AnchorState.found if found else AnchorState.missing)


def place_source(placement: SignaturePlacement, origin: PlacementOrigin) -> PlaceSource | None:
    """Какой формой пака задано место, по которому стоит размещение; None у ручного (15.17.14)."""
    if origin is PlacementOrigin.manual:
        return None
    if origin is PlacementOrigin.pack and placement.from_pack is not None and placement.from_pack.anchor is not None:
        return PlaceSource.anchor
    return PlaceSource.mm


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


def stamp_from_pack(
    placement: SignaturePlacement, version: str, *, anchor: str | None = None, build: str | None = None
) -> SignaturePlacement:
    """Пометить размещение местом из шаблона версии `version` с отпечатком его текущего места и меток.

    `anchor` и `build` у места на якоре (15.17.10): id якоря записи и сборка, по якорям которой место посчитано.
    """
    mark = FromPack(version=version, digest=placement_digest(placement), anchor=anchor, build=build)
    return replace(placement, from_pack=mark)


def keep_from_pack(before: SignaturePlacement, after: SignaturePlacement) -> SignaturePlacement:
    """Системная правка места (расширение под плашку ЭП) не делает место из шаблона ручным.

    Если до правки место было как в шаблоне, пометка переписывается под новую геометрию с той же версией; иначе
    размещение остаётся как есть (ручное место остаётся ручным, пометки нет).
    """
    if before.from_pack is None or not is_from_pack(before):
        return after
    return replace(after, from_pack=replace(before.from_pack, digest=placement_digest(after)))


def clear_from_pack(placement: SignaturePlacement) -> SignaturePlacement:
    """Правка человеком снимает пометку «место из шаблона» (15.4)."""
    return placement if placement.from_pack is None else replace(placement, from_pack=None)


def pack_marks(slot_def: SignatureSlotDef, doc_def_id: str, src: SourceAnchors = NO_ANCHORS) -> tuple[DateMark, ...]:
    """Метки даты пака для документа как метки размещения: у пака их id нет, сервер назначает `d1`, `d2`, ...

    Метки на якоре считаются по якорям источника (`resolve_mark`); метка без якоря и без запасной не ставится.
    """
    resolved = (resolve_mark(mark, src) for mark in slot_def.dates_for(doc_def_id))
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
        for number, mark in enumerate((m for m in resolved if m is not None), start=1)
    )


def pack_placement(
    slot_def: SignatureSlotDef,
    doc_def_id: str,
    base: SignaturePlacement | None,
    version: str,
    src: SourceAnchors = NO_ANCHORS,
) -> SignaturePlacement | None:
    """Место и метки даты слота на документе как в шаблоне версии `version`, с пометкой `from_pack` (15.5, 15.6).

    Включённость, дата в рамке и момент подписи берутся у `base` (без него место выключено): их не задаёт пак и не
    учитывает отпечаток. Включает место тот, кто применяет пресет, а «Вернуть место из шаблона» её не меняет.

    Место на якоре считается по якорям источника подписи `src` (15.17.8); None, если места нет: якоря известны, а
    нужного нет (или рамка за краем листа), якоря неизвестны и запасного места нет, источник это свой PDF. Пометка
    места на якоре несёт id якоря и сборку, по якорям которой оно посчитано (у запасного места сборки нет).
    """
    entry = slot_def.entry_for(doc_def_id)
    place = resolve_place(entry, src)
    if place is None:
        return None
    start = base or SignaturePlacement(
        enabled=False, page=place.page, x_mm=place.x_mm, y_mm=place.y_mm, width_mm=place.width_mm
    )
    placement = replace(
        start,
        page=place.page,
        x_mm=place.x_mm,
        y_mm=place.y_mm,
        width_mm=place.width_mm,
        dates=pack_marks(slot_def, doc_def_id, src),
    )
    anchored = slot_def.uses_anchors(doc_def_id)
    anchor = entry.anchor if isinstance(entry, AnchorPlace) else None
    build = src.anchors.build if anchored and src.known and src.anchors is not None else None
    return stamp_from_pack(placement, version, anchor=anchor, build=build)
