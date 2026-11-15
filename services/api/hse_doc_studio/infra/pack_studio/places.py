"""Места подписей и метки даты в `version.yaml` (docs/design/template-studio.md, 5.6, срез T9): порт `IPackPlaces`.

Модель читается тем же лоадером пака, что и у проекта (`parse_signature_slot`, `parse_default_date`), рамки сборки
считает `core/signatures/pack_places` (`resolve_place`, `resolve_mark`). Запись идёт точечными правками YAML
(`yaml_edits`, D11): меняется только фрагмент записи, комментарии и выравнивание соседей остаются.

Как правка ложится в YAML:

- место на якоре двигается относительно своей линии (`align` прежний, `dx_mm`, `dy_mm` и ширина по рамке), запасное
  место в мм остаётся как было; у сборки без якорей двигается само запасное место (его рамку автор и видит);
- новое место документа встаёт на строку шаблона, если в сборке есть якорь подписи с id слота на той же странице
  (`align: left`, запасное место это рамка сейчас); иначе место в мм;
- метка даты на якоре двигается относительно линии так же; новая метка на строку ставится только явно (`anchor`);
- координаты округляются до 1 мм, как у «Скопировать как пресет шаблона» (раздел 13); ширина места от 10 мм;
- запись пишется одной строкой `{ ... }` в порядке ключей справки; запись, которой больше нет, уходит вместе с
  опустевшим `placements` или `default_dates`.

Каждая запись перед записью проверяется строгим разбором лоадера: рамка за краем листа или запись на якоре без
запасного места у `default_placement` это `PlaceEditError`, файл не меняется.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, replace
from typing import Any

import yaml

from hse_doc_studio.core.catalog import (
    ANCHOR_DATE_HEIGHT_MM,
    ANCHOR_DEFAULT_DY_MM,
    AnchorDate,
    AnchorPlace,
    PackDate,
    PackPlace,
    SignatureDefaultDate,
    SignatureDefaultPlacement,
    SignatureSlotDef,
)
from hse_doc_studio.core.enums import AnchorState, DateMarkAlign, DateMarkFormat
from hse_doc_studio.core.pack_studio.places import (
    AnchorRef,
    DocDate,
    DocFrame,
    FrameKind,
    MarkBox,
    PlaceBox,
    PlaceEditError,
    PlaceOp,
    PlaceOpKind,
    SlotPlaces,
    VersionPlaces,
)
from hse_doc_studio.core.signatures.anchors import AnchorKind, BuildAnchor, BuildAnchors, is_anchor_id
from hse_doc_studio.core.signatures.dates import MAX_DATE_MARKS, SHEET_HEIGHT_MM, SHEET_WIDTH_MM
from hse_doc_studio.core.signatures.pack_places import SourceAnchors, aligned_x, resolve_mark, resolve_place
from hse_doc_studio.infra.pack_studio.yaml_edits import delete, insert_item, set_value
from hse_doc_studio.infra.template.yaml_template_repository import (
    PLACE_MAX_WIDTH_MM,
    PLACE_MAX_Y_MM,
    PLACE_MIN_WIDTH_MM,
    parse_default_anchor,
    parse_default_date,
    parse_mm_placement,
    parse_signature_slot,
    parse_slot_placement,
)

_LOADER: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_SLOTS = ("signatures", "slots")
# Путь до словаря слота: ("signatures", "slots", индекс).
_SLOT_DEPTH = 3
_DATE_MIN_HEIGHT_MM = 2.0
_DATE_MAX_HEIGHT_MM = 20.0
# Ширина рамки метки на строке-точке (якорь без ширины линии).
_POINT_DATE_WIDTH_MM = 20.0
# Метка на якоре «не сдвинута» по ширине, если разница с линией не больше этого (округление до 1 мм).
_SAME_MM = 0.5
_PARSE_ERRORS = (TypeError, ValueError, KeyError)
_MISSING = object()

Path = tuple[str | int, ...]


# ── чтение ──────────────────────────────────────────────────────────────────


def _load(text: str) -> dict[str, Any]:
    try:
        data = yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик (CSafeLoader или SafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"version.yaml is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise TypeError("version.yaml is not a mapping")
    return data


def _raw_slots(data: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """Слоты каталога с индексом в списке YAML; не словари пропускаются, индексы остальных не сдвигаются."""
    signatures = data.get("signatures")
    slots = signatures.get("slots") if isinstance(signatures, dict) else None
    if not isinstance(slots, list):
        return []
    return [(i, raw) for i, raw in enumerate(slots) if isinstance(raw, dict) and "id" in raw]


def _documents(data: dict[str, Any]) -> tuple[str, ...]:
    """Ростер версии: id строками (раскладка с `doc.yaml`) или словари с `id` (документы в манифесте)."""
    roster = data.get("documents")
    if not isinstance(roster, list):
        return ()
    ids = (item.get("id") if isinstance(item, dict) else item for item in roster)
    return tuple(doc for doc in ids if isinstance(doc, str))


def _anchor_ids(anchors: BuildAnchors | None, kind: AnchorKind) -> tuple[str, ...]:
    return tuple(a.id for a in anchors.anchors if a.kind is kind) if anchors is not None else ()


def _parsed_marks(doc_id: str, items: list[Any]) -> Iterator[tuple[int, PackDate]]:
    for i, item in enumerate(items):
        try:
            yield i, parse_default_date(item, f"default_dates.{doc_id}[{i}]")
        except _PARSE_ERRORS:
            continue


def _raw_dates(raw: dict[str, Any]) -> tuple[tuple[str, tuple[tuple[int, PackDate], ...]], ...]:
    """Метки даты по документам с индексом в списке YAML; битая метка пропускается одна."""
    by_doc = raw.get("default_dates")
    if not isinstance(by_doc, dict):
        return ()
    return tuple(
        (str(doc_id), tuple(_parsed_marks(str(doc_id), items)))
        for doc_id, items in by_doc.items()
        if isinstance(items, list)
    )


def _ref(entry: PackPlace | PackDate, src: SourceAnchors) -> AnchorRef | None:
    if not isinstance(entry, AnchorPlace | AnchorDate):
        return None
    if not src.known:
        return AnchorRef(entry.anchor, AnchorState.unknown)
    return AnchorRef(entry.anchor, AnchorState.found if src.line(entry.anchor) is not None else AnchorState.missing)


def _frame(
    slot: SignatureSlotDef, dates: tuple[tuple[int, PackDate], ...], document: str, src: SourceAnchors
) -> DocFrame:
    explicit = dict(slot.placements).get(document)
    entry = explicit if explicit is not None else slot.entry_for(document)
    return DocFrame(
        kind=FrameKind.place if explicit is not None else FrameKind.default,
        entry=entry,
        box=resolve_place(entry, src),
        anchor=_ref(entry, src),
        dates=tuple(DocDate(i, mark, resolve_mark(mark, src), _ref(mark, src)) for i, mark in dates),
    )


def _slot_view(raw: dict[str, Any], document: str | None, src: SourceAnchors) -> SlotPlaces | None:
    try:
        slot = parse_signature_slot(raw)
    except _PARSE_ERRORS:
        return None
    dates = _raw_dates(raw)
    frame = None
    if document is not None and document in slot.applies_to:
        frame = _frame(slot, dict(dates).get(document, ()), document, src)
    return SlotPlaces(
        id=slot.id,
        label=slot.label,
        applies_to=slot.applies_to,
        per_author=slot.per_author,
        required=slot.required,
        default_place=slot.default_anchor if slot.default_anchor is not None else slot.default_placement,
        default_set="default_placement" in raw,
        places=slot.placements,
        dates=dates,
        document=frame,
    )


# ── запись ──────────────────────────────────────────────────────────────────


def _n(value: float) -> int:
    """Миллиметры до 1 мм (как пресет из проекта, раздел 13); `+ 0` убирает минус у нуля."""
    return round(value) + 0


def _child(node: Any, key: str | int) -> Any:
    if isinstance(node, dict):
        return node.get(key, _MISSING)
    if isinstance(node, list) and isinstance(key, int) and 0 <= key < len(node):
        return node[key]
    return _MISSING


def _node(text: str, path: Path) -> Any:
    """Узел по пути в разобранном тексте; `_MISSING`, если его нет."""
    node: Any = _load(text)
    for key in path:
        node = _child(node, key)
        if node is _MISSING:
            break
    return node


def _create(text: str, path: Path, value: Any, *, after: str | None) -> str:
    """Значение по пути; если нет родителя (`placements`, `default_dates`), он создаётся с этим ключом."""
    if _node(text, path[:-1]) is _MISSING:
        return set_value(text, path[:-1], {path[-1]: value}, after=after)
    return set_value(text, path, value, after=after)


def _write(text: str, path: Path, value: dict[str, Any], *, after: str | None = None) -> str:
    """Запись-словарь по пути одной строкой `{ ... }` с ключами в порядке `value`.

    Тот же набор ключей в том же порядке правится на месте; иначе запись сначала сводится к первому ключу, а
    остальные дописываются по одному: так длинная запись остаётся одной строкой, как в паках.
    """
    current = _node(text, path)
    if isinstance(current, dict) and list(current) == list(value):
        return set_value(text, path, value)
    first = next(iter(value))
    text = _create(text, path, {first: value[first]}, after=after)
    return set_value(text, path, value)


def _append(text: str, path: Path, item: dict[str, Any], *, after: str | None) -> str:
    """Элемент в конец списка по пути (список и его родитель создаются), одной строкой."""
    first = next(iter(item))
    seed = {first: item[first]}
    current = _node(text, path)
    if isinstance(current, list):
        index = len(current)
        text = insert_item(text, path, index, seed)
    else:
        index = 0
        text = _create(text, path, [seed], after=after)
    return set_value(text, (*path, index), item)


def _remove(text: str, path: Path) -> str:
    """Ключ или элемент по пути; опустевший `placements`, `default_dates` или список меток уходит вместе с ним."""
    parent = _node(text, path[:-1])
    if len(path) > _SLOT_DEPTH + 1 and isinstance(parent, dict | list) and len(parent) == 1:
        return _remove(text, path[:-1])
    return delete(text, path)


def _mm_place_item(place: SignatureDefaultPlacement) -> dict[str, Any]:
    return {"page": place.page, "x_mm": _n(place.x_mm), "y_mm": _n(place.y_mm), "width_mm": _n(place.width_mm)}


def _place_item(entry: PackPlace) -> dict[str, Any]:
    """Запись места в порядке справки; поля со значением лоадера по умолчанию не пишутся."""
    if isinstance(entry, SignatureDefaultPlacement):
        return _mm_place_item(entry)
    item: dict[str, Any] = {"anchor": entry.anchor}
    if entry.align is not DateMarkAlign.centered:
        item["align"] = entry.align.value
    if _n(entry.dx_mm) != 0:
        item["dx_mm"] = _n(entry.dx_mm)
    if _n(entry.dy_mm) != ANCHOR_DEFAULT_DY_MM:
        item["dy_mm"] = _n(entry.dy_mm)
    return item | _width_and_fallback(entry.width_mm, entry.fallback)


def _width_and_fallback(width: float | None, fallback: SignatureDefaultPlacement | None) -> dict[str, Any]:
    if fallback is None:
        return {} if width is None else {"width_mm": _n(width)}
    mm = _mm_place_item(fallback)
    return {
        "width_mm": _n(width) if width is not None else mm["width_mm"],
        **{k: mm[k] for k in ("page", "x_mm", "y_mm")},
    }


def _mm_date_item(mark: SignatureDefaultDate) -> dict[str, Any]:
    item: dict[str, Any] = {
        "page": mark.page,
        "x_mm": _n(mark.x_mm),
        "y_mm": _n(mark.y_mm),
        "width_mm": _n(mark.width_mm),
        "height_mm": _n(mark.height_mm),
        "format": DateMarkFormat(mark.format).value,
    }
    if mark.align is not DateMarkAlign.centered:
        item["align"] = mark.align.value
    return item


def _date_item(entry: PackDate) -> dict[str, Any]:
    """Запись метки даты в порядке справки; `format` только если он не часть якоря."""
    if isinstance(entry, SignatureDefaultDate):
        return _mm_date_item(entry)
    item: dict[str, Any] = {"anchor": entry.anchor}
    if entry.anchor.partition(".")[2] != entry.format.value:
        item["format"] = entry.format.value
    if entry.align is not DateMarkAlign.centered:
        item["align"] = entry.align.value
    if _n(entry.height_mm) != ANCHOR_DATE_HEIGHT_MM:
        item["height_mm"] = _n(entry.height_mm)
    return item | _date_tail(entry)


def _date_tail(entry: AnchorDate) -> dict[str, Any]:
    tail: dict[str, Any] = {}
    width = entry.width_mm if entry.width_mm is not None else (entry.fallback.width_mm if entry.fallback else None)
    if width is not None:
        tail["width_mm"] = _n(width)
    if _n(entry.dx_mm) != 0:
        tail["dx_mm"] = _n(entry.dx_mm)
    if entry.dy_mm is not None:
        tail["dy_mm"] = _n(entry.dy_mm)
    if entry.fallback is not None:
        tail |= {"page": entry.fallback.page, "x_mm": _n(entry.fallback.x_mm), "y_mm": _n(entry.fallback.y_mm)}
    return tail


def _checked(parse: Callable[[Any, str], object], item: dict[str, Any], where: str) -> dict[str, Any]:
    try:
        parse(item, where)
    except _PARSE_ERRORS as exc:
        raise PlaceEditError(str(exc)) from None
    return item


def _parse_place(item: Any, where: str) -> object:
    return parse_default_anchor(item) if "anchor" in item else parse_mm_placement(item, where)


def _round_box(box: PlaceBox) -> SignatureDefaultPlacement:
    """Рамка места до 1 мм, ширина от 10 до 200 мм, по ширине внутри листа, верх не ниже 287 мм."""
    width = min(PLACE_MAX_WIDTH_MM, max(PLACE_MIN_WIDTH_MM, round(box.width_mm)))
    x = min(max(0, round(box.x_mm)), SHEET_WIDTH_MM - width)
    y = min(max(0, round(box.y_mm)), PLACE_MAX_Y_MM)
    return SignatureDefaultPlacement(page=max(1, box.page), x_mm=x, y_mm=y, width_mm=width)


def _round_mark(mark: MarkBox) -> SignatureDefaultDate:
    width = max(1, round(mark.width_mm))
    height = max(1, round(mark.height_mm))
    return SignatureDefaultDate(
        page=max(1, mark.page),
        x_mm=min(max(0, round(mark.x_mm)), SHEET_WIDTH_MM - width),
        y_mm=min(max(0, round(mark.y_mm)), SHEET_HEIGHT_MM - height),
        width_mm=width,
        height_mm=height,
        format=mark.format,
        align=mark.align,
    )


def _relative(
    anchor: str, align: DateMarkAlign, line: BuildAnchor, box: PlaceBox, fallback: SignatureDefaultPlacement | None
) -> AnchorPlace:
    """Место относительно линии якоря: рамка `box` этой сборки при выравнивании `align`."""
    width = _round_box(box).width_mm
    return AnchorPlace(
        anchor=anchor,
        align=align,
        dx_mm=_n(box.x_mm - aligned_x(align, line, width)),
        dy_mm=_n(box.y_mm - line.y_mm),
        width_mm=width,
        fallback=fallback,
    )


def _sign_line(anchors: BuildAnchors | None, anchor_id: str) -> BuildAnchor | None:
    line = anchors.get(anchor_id) if anchors is not None else None
    return line if line is not None and line.kind is AnchorKind.sign else None


@dataclass(frozen=True)
class _Target:
    """Слот правки в тексте манифеста: индекс в списке, сырой словарь, разобранный слот и якоря сборки."""

    text: str
    index: int
    raw: dict[str, Any]
    slot: SignatureSlotDef
    documents: tuple[str, ...]
    anchors: BuildAnchors | None

    def path(self, *rest: str | int) -> Path:
        return (*_SLOTS, self.index, *rest)

    @property
    def src(self) -> SourceAnchors:
        return SourceAnchors(self.anchors)

    def doc(self, doc: str | None) -> str:
        """Документ правки: есть в версии и слот к нему применим."""
        if doc is None:
            raise PlaceEditError("the operation needs a document")
        if (self.documents and doc not in self.documents) or doc not in self.slot.applies_to:
            raise PlaceEditError(f"slot {self.slot.id!r} does not apply to document {doc!r}")
        return doc

    def explicit(self, doc: str) -> PackPlace | None:
        return dict(self.slot.placements).get(doc)

    def marks(self, doc: str) -> list[Any]:
        by_doc = self.raw.get("default_dates")
        items = by_doc.get(doc) if isinstance(by_doc, dict) else None
        return items if isinstance(items, list) else []


def _target(text: str, slot_id: str, anchors: BuildAnchors | None) -> _Target:
    data = _load(text)
    for index, raw in _raw_slots(data):
        if raw.get("id") == slot_id:
            try:
                slot = parse_signature_slot(raw)
            except _PARSE_ERRORS as exc:
                raise PlaceEditError(f"slot {slot_id!r} cannot be read: {exc}") from None
            return _Target(text, index, raw, slot, _documents(data), anchors)
    raise PlaceEditError(f"slot {slot_id!r} is not in the catalog of this version")


def _need[T](value: T | None, name: str) -> T:
    if value is None:
        raise PlaceEditError(f"the operation needs {name}")
    return value


def _write_place(t: _Target, doc: str | None, entry: PackPlace) -> str:
    item = _place_item(entry)
    if doc is None:
        return _write(t.text, t.path("default_placement"), _checked(_parse_place, item, "default_placement"))
    checked = _checked(parse_slot_placement, item, f"placements.{doc}")
    return _write(t.text, t.path("placements", doc), checked, after="default_placement")


def _moved(current: AnchorPlace, box: PlaceBox, anchors: BuildAnchors | None) -> PackPlace:
    """Место на якоре после перетаскивания рамки этой сборки."""
    line = anchors.get(current.anchor) if anchors is not None else None
    if line is not None and line.page == box.page:
        return _relative(current.anchor, current.align, line, box, current.fallback)
    rounded = _round_box(box)
    if anchors is None and current.fallback is not None:
        # Якорей у сборки нет: рамка на листе это запасное место, его и двигаем.
        return replace(current, width_mm=rounded.width_mm, fallback=rounded)
    return rounded


def _set_place(t: _Target, op: PlaceOp) -> str:
    box = _need(op.box, "box")
    if op.doc is None:
        current = t.slot.default_anchor
        return _write_place(t, None, _moved(current, box, t.anchors) if current is not None else _round_box(box))
    doc = t.doc(op.doc)
    explicit = t.explicit(doc)
    if isinstance(explicit, AnchorPlace):
        entry: PackPlace = _moved(explicit, box, t.anchors)
    elif explicit is None and (line := _sign_line(t.anchors, t.slot.id)) is not None and line.page == box.page:
        # Новое место документа встаёт на строку шаблона: верстка с другими данными его не собьёт.
        entry = _relative(t.slot.id, DateMarkAlign.left, line, box, _round_box(box))
    else:
        entry = _round_box(box)
    return _write_place(t, doc, entry)


def _remove_place(t: _Target, op: PlaceOp) -> str:
    doc = _need(op.doc, "a document")
    if _node(t.text, t.path("placements", doc)) is _MISSING:
        raise PlaceEditError(f"slot {t.slot.id!r} has no place of its own on document {doc!r}")
    return _remove(t.text, t.path("placements", doc))


def _make_default(t: _Target, op: PlaceOp) -> str:
    doc = t.doc(op.doc)
    entry = t.explicit(doc)
    if entry is None:
        raise PlaceEditError(f"slot {t.slot.id!r} has no place of its own on document {doc!r}")
    if isinstance(entry, AnchorPlace) and entry.fallback is None:
        # Общее место на якоре читают все версии Студии только с запасным местом в мм (15.17.7).
        resolved = resolve_place(entry, t.src)
        entry = replace(entry, fallback=resolved if resolved is not None else t.slot.default_placement)
    text = _write_place(t, None, entry)
    return _remove(text, t.path("placements", doc))


def _current_entry(t: _Target, doc: str | None) -> PackPlace:
    if doc is None:
        return t.slot.default_anchor if t.slot.default_anchor is not None else t.slot.default_placement
    return t.slot.entry_for(t.doc(doc))


def _bind(t: _Target, op: PlaceOp) -> str:
    line = _sign_line(t.anchors, t.slot.id)
    if line is None:
        raise PlaceEditError(f"the build has no template line for slot {t.slot.id!r}")
    current = _current_entry(t, op.doc)
    resolved = resolve_place(current, t.src)
    box = resolved if resolved is not None else t.slot.place_for(op.doc or "")
    if box.page != line.page:
        raise PlaceEditError(f"the template line of slot {t.slot.id!r} is on page {line.page}")
    frame = PlaceBox(box.page, box.x_mm, box.y_mm, box.width_mm)
    return _write_place(t, op.doc, _relative(t.slot.id, DateMarkAlign.left, line, frame, _round_box(frame)))


def _unbind(t: _Target, op: PlaceOp) -> str:
    current = _current_entry(t, op.doc)
    if not isinstance(current, AnchorPlace):
        raise PlaceEditError(f"the place of slot {t.slot.id!r} is not on a template line")
    resolved = resolve_place(current, t.src) or current.fallback
    if resolved is None:
        raise PlaceEditError(f"the template line of slot {t.slot.id!r} is not in this build and there is no fallback")
    return _write_place(t, op.doc, _round_box(PlaceBox(resolved.page, resolved.x_mm, resolved.y_mm, resolved.width_mm)))


def _anchored_new(t: _Target, anchor: str, mark: MarkBox | None) -> AnchorDate:
    """Новая метка на строке даты сборки: по умолчанию на линии, ширина линии (у точки 20 мм)."""
    line = t.anchors.get(anchor) if t.anchors is not None and is_anchor_id(anchor, AnchorKind.date) else None
    if line is None or line.kind is not AnchorKind.date:
        raise PlaceEditError(f"the build has no date line {anchor!r}")
    part = anchor.partition(".")[2]
    known = part in DateMarkFormat.__members__.values()
    fmt = DateMarkFormat(part) if known else (mark.format if mark is not None else DateMarkFormat.date_numeric)
    return AnchorDate(anchor=anchor, format=fmt, width_mm=None if line.width_mm > 0 else _POINT_DATE_WIDTH_MM)


def _add_date(t: _Target, op: PlaceOp) -> str:
    doc = t.doc(op.doc)
    if len(t.marks(doc)) >= MAX_DATE_MARKS:
        raise PlaceEditError(f"document {doc!r} already has {MAX_DATE_MARKS} date marks of slot {t.slot.id!r}")
    entry: PackDate = (
        _anchored_new(t, op.anchor, op.mark) if op.anchor is not None else _round_mark(_need(op.mark, "a date mark"))
    )
    item = _checked(parse_default_date, _date_item(entry), f"default_dates.{doc}[new]")
    return _append(t.text, t.path("default_dates", doc), item, after="placements")


def _moved_mark(
    current: AnchorDate, mark: SignatureDefaultDate, raw: MarkBox, anchors: BuildAnchors | None
) -> PackDate:
    line = anchors.get(current.anchor) if anchors is not None else None
    if line is not None and line.page == mark.page:
        height = min(_DATE_MAX_HEIGHT_MM, max(_DATE_MIN_HEIGHT_MM, mark.height_mm))
        same_width = current.width_mm is None and abs(raw.width_mm - line.width_mm) <= _SAME_MM
        width = None if same_width else mark.width_mm
        dy = _n(raw.y_mm - line.y_mm)
        return AnchorDate(
            anchor=current.anchor,
            format=mark.format,
            height_mm=height,
            width_mm=width,
            dx_mm=_n(raw.x_mm - aligned_x(mark.align, line, width if width is not None else line.width_mm)),
            dy_mm=None if dy == -height else dy,
            align=mark.align,
            fallback=current.fallback,
        )
    if anchors is None and current.fallback is not None:
        return replace(
            current,
            format=mark.format,
            align=mark.align,
            width_mm=mark.width_mm,
            height_mm=mark.height_mm,
            fallback=mark,
        )
    return mark


def _set_date(t: _Target, op: PlaceOp) -> str:
    doc = t.doc(op.doc)
    index = _need(op.index, "a date mark index")
    items = t.marks(doc)
    if not 0 <= index < len(items):
        raise PlaceEditError(f"document {doc!r} has no date mark {index} of slot {t.slot.id!r}")
    raw = _need(op.mark, "a date mark")
    mark = _round_mark(raw)
    try:
        current: PackDate | None = parse_default_date(items[index], f"default_dates.{doc}[{index}]")
    except _PARSE_ERRORS:
        current = None
    entry = _moved_mark(current, mark, raw, t.anchors) if isinstance(current, AnchorDate) else mark
    item = _checked(parse_default_date, _date_item(entry), f"default_dates.{doc}[{index}]")
    return _write(t.text, t.path("default_dates", doc, index), item)


def _remove_date(t: _Target, op: PlaceOp) -> str:
    doc = _need(op.doc, "a document")
    index = _need(op.index, "a date mark index")
    if not 0 <= index < len(t.marks(doc)):
        raise PlaceEditError(f"document {doc!r} has no date mark {index} of slot {t.slot.id!r}")
    return _remove(t.text, t.path("default_dates", doc, index))


_HANDLERS: dict[PlaceOpKind, Callable[[_Target, PlaceOp], str]] = {
    PlaceOpKind.set_place: _set_place,
    PlaceOpKind.remove_place: _remove_place,
    PlaceOpKind.make_default: _make_default,
    PlaceOpKind.bind_anchor: _bind,
    PlaceOpKind.unbind_anchor: _unbind,
    PlaceOpKind.add_date: _add_date,
    PlaceOpKind.set_date: _set_date,
    PlaceOpKind.remove_date: _remove_date,
}


class PackPlacesEditor:
    """Реализация порта `IPackPlaces` (core/pack_studio/protocols.py)."""

    def describe(self, text: str, *, document: str | None, anchors: BuildAnchors | None) -> VersionPlaces:
        data = _load(text)
        src = SourceAnchors(anchors)
        views = (_slot_view(raw, document, src) for _, raw in _raw_slots(data))
        return VersionPlaces(
            documents=_documents(data),
            slots=tuple(view for view in views if view is not None),
            document=document,
            anchors_known=anchors is not None,
            sign_anchors=_anchor_ids(anchors, AnchorKind.sign),
            date_anchors=_anchor_ids(anchors, AnchorKind.date),
        )

    def apply(self, text: str, ops: Sequence[PlaceOp], *, document: str | None, anchors: BuildAnchors | None) -> str:
        # Якоря сборки годятся только для её документа: правка другого документа идёт без них.
        for op in ops:
            usable = anchors if op.doc is None or op.doc == document else None
            text = _HANDLERS[op.op](_target(text, op.slot, usable), op)
        return text
