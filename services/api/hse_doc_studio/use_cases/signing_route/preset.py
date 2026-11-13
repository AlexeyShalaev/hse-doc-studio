"""Пресет маршрута точки на проекте и его применение к состоянию подписей (docs/design/signing-route.md, 15.5, 15.6).

`route_preset` раскладывает `signing_slots` профиля на документы и рантайм-слоты проекта: запись пака называет id
определения документа и слот каталога, а в проекте это экземпляры документов и слоты команды (`author--<слаг>`).
Записи, которые к проекту не применимы (документа нет в точке, слот не ставится на документ, пару требует точка, а
условие задано), лоадер не отбрасывает, и здесь они молча пропускаются: проверка их связи с `items` это `pack_lint`.

`apply_preset_files` пишет то, что пресет меняет в файлах: отметки `optional` пар маршрута и места с метками даты
(`from_pack`). Чистые функции над `SignaturesState`, их зовут сценарии маршрута под `route_files`.

Что не трогается никогда: ручные места (место с `from_pack`, отпечаток которого разошёлся, и любое место без пометки,
кроме затравки), документы под другим маршрутом (`HOLDING_STATUSES`), места на документах, над зафиксированным PDF
которых уже есть ЭП (новое место устарило бы фиксацию и сбросило бы чужие подписи, как в 15.9), места слота
`per_author` на общем документе команды (15.5) и отметки слотов, которые пак запрещает делать необязательными.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass, replace

from hse_doc_studio.core.catalog import AnchorPlace, SubmissionProfile, TemplateVersion
from hse_doc_studio.core.enums import PlacementOrigin
from hse_doc_studio.core.services import SignatureSlotService
from hse_doc_studio.core.signatures.pack_places import NO_ANCHORS, SourceAnchors, pack_placement
from hse_doc_studio.core.signatures.plan import SignMethod, VisibleMark, mark_of, method_of
from hse_doc_studio.core.signatures.route_order import default_route
from hse_doc_studio.core.signing_route.entities import DocSlot
from hse_doc_studio.core.signing_route.preset import PresetSlot, RoutePreset, condition_met
from hse_doc_studio.core.team import is_team, split_instance_id
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState
from hse_doc_studio.use_cases.signatures.pack_places import PackPlaces
from hse_doc_studio.use_cases.signatures.set_slot_optional import with_optional, without_skip
from hse_doc_studio.use_cases.signing_route.point import RoutePoint

# Места, которые пресет ставит при создании черновика с нуля (15.5): места нет, оно как в шаблоне или затравка.
FRESH_ORIGINS = frozenset({None, PlacementOrigin.pack, PlacementOrigin.seed})
# Черновик после прежнего маршрута точки (15.5): только пары без места (затравка, новая пара).
INHERITED_ORIGINS = frozenset({None, PlacementOrigin.seed})


def has_preset(version: TemplateVersion, profile: SubmissionProfile) -> bool:
    """Задаёт ли версия шаблона пресет точки: `signing_slots` профиля или места и метки даты слотов по документам.

    Без них (все выпущенные версии до 2026.1.4) пак даёт только порядок 5.2 и общее `default_placement`, и маршрут
    ведёт себя как до раздела 15: черновик ничего не пишет в файлы, у маршрута нет `preset`.
    """
    if profile.signing_slots:
        return True
    return any(
        slot.placements or slot.default_dates or slot.default_anchor is not None
        for slot in version.signatures_config.slots
    )


def _pairs_of(point: RoutePoint, doc_def_id: str, slot_id: str) -> list[DocSlot]:
    """Пары проекта записи пресета: экземпляры документа точки и рантайм-слоты слота каталога, применимые к ним."""
    service = SignatureSlotService()
    point_docs = set(point.docs_of(point.required))
    return [
        DocSlot(doc.id, runtime.id)
        for doc in point.project.documents
        if doc.def_id == doc_def_id and doc.id in point_docs and doc.id in point.documents
        for runtime in point.runtime.values()
        if split_instance_id(runtime.id)[0] == slot_id and service.slot_applies_to_doc(runtime, doc)
    ]


def _forbidden(point: RoutePoint, pair: DocSlot) -> bool:
    """Пак запрещает отмечать эту подпись необязательной (`required: true`, 13.3), или слота нет в проекте."""
    slot = point.runtime.get(pair.slot_id)
    return slot is None or slot.required


def _entries(point: RoutePoint) -> tuple[list[PresetSlot], list[PresetSlot], list[DocSlot]]:
    """Записи `signing_slots` на парах проекта: слоты сверх точки с выполненным условием, слоты, которые условие
    не пропустило, и пары, которые пресет отмечает необязательными (пары точки и включённые сверх точки)."""
    extras: list[PresetSlot] = []
    skipped: list[PresetSlot] = []
    marked: list[DocSlot] = []
    for entry in point.profile.signing_slots:
        for pair in _pairs_of(point, entry.doc_id, entry.slot_id):
            if pair not in point.allowed and not point.is_optional(pair):
                continue
            if pair not in point.allowed and not condition_met(entry.when, point.project):
                skipped.append(PresetSlot(pair, entry.when))
                continue
            if pair not in point.allowed:
                extras.append(PresetSlot(pair, entry.when))
            if entry.optional and not _forbidden(point, pair):
                marked.append(pair)
    return extras, skipped, marked


def route_preset(point: RoutePoint) -> RoutePreset | None:
    """Пресет точки на проекте сейчас; None, если версия шаблона пресета не задаёт (`has_preset`) или точке подписи
    не нужны."""
    if not has_preset(point.version, point.profile):
        return None
    extras, skipped, marked = _entries(point)
    extra_pairs = [item.pair for item in extras]
    steps = default_route(
        point.version,
        point.profile,
        point.project,
        slot_ids=[pair.slot_id for pair in (*point.required, *extra_pairs)],
    )
    if not steps:
        # Точке подписи не нужны (в КП «Расширенная заявка», «Предзащита»): маршрута нет, нечего и задавать.
        return None
    optional = tuple(dict.fromkeys(marked))
    return RoutePreset(
        version=point.version.version,
        steps=steps,
        extra_slots=tuple(dict.fromkeys(extras)),
        optional=optional,
        skipped_by_condition=tuple(dict.fromkeys(skipped)),
    )


def mark_may_show(point: RoutePoint, pair: DocSlot, state: SignaturesState) -> bool:
    """Будет ли у слота видимая метка. Если способ слота точка не принимает, его выберет подписант (6.3): место
    нужно, когда хотя бы один разрешённый способ ставит картинку или плашку (все, кроме PAdES без метки)."""
    slot = state.slots.get(pair.slot_id)
    allowed = point.allowed.get(pair, ())
    method = method_of(slot.sign_mode) if slot is not None else SignMethod.image
    if allowed and method.value not in allowed:
        return any(name != SignMethod.pades.value for name in allowed)
    return mark_of(slot) is not VisibleMark.none


def signed_over_frozen(state: SignaturesState, doc_id: str) -> bool:
    """Над зафиксированным PDF документа уже есть ЭП: новое место устарило бы фиксацию и сбросило бы их."""
    return doc_id in state.frozen and bool(state.detached.get(doc_id) or state.embedded.get(doc_id))


@dataclass(frozen=True)
class PresetApplied:
    """Что применение пресета записало: новое состояние и пары, которым поставлены место и отметка."""

    state: SignaturesState
    placed: tuple[DocSlot, ...] = ()
    marked: tuple[DocSlot, ...] = ()
    unmarked: tuple[DocSlot, ...] = ()


def _shared_per_author(point: RoutePoint, pair: DocSlot) -> bool:
    """Слот `per_author` на общем документе команды: все авторы встали бы в одну рамку, место ставит команда."""
    runtime = point.runtime.get(pair.slot_id)
    doc = point.documents.get(pair.doc_id)
    return (
        is_team(point.project)
        and runtime is not None
        and runtime.slot_def.per_author
        and doc is not None
        and (doc.owner is None)
    )


def apply_places(  # noqa: PLR0913 — что применить и к чему
    point: RoutePoint,
    state: SignaturesState,
    pairs: Iterable[DocSlot],
    places: PackPlaces,
    *,
    origins: Collection[PlacementOrigin | None],
    skip_docs: Collection[str] = (),
    anchors: Mapping[str, SourceAnchors] | None = None,
) -> tuple[SignaturesState, tuple[DocSlot, ...]]:
    """Места и метки даты пресета у пар, где места нет или оно из `origins` (15.5); места включаются, если метка
    может появиться (`mark_may_show`). Ручные места, документы `skip_docs`, документы с ЭП над B и `per_author` на
    общем документе команды не трогаются.

    Место на якоре считается по якорям источника подписи документа (`anchors`, 15.17.8). Нет места (якоря
    известны, а строки нет; свой PDF; якоря неизвестны без запасного места) или якоря неизвестны, а место уже
    стоит: пара не трогается.
    """
    placed: list[DocSlot] = []
    known = anchors or {}
    for pair in dict.fromkeys(pairs):
        if pair.doc_id in skip_docs:
            continue
        existing = state.placements.get(pair.doc_id, {}).get(pair.slot_id)
        placement = _preset_place(point, state, pair, places, origins, known.get(pair.doc_id, NO_ANCHORS))
        if placement is None or placement == existing:
            continue
        doc_placements = {**state.placements.get(pair.doc_id, {}), pair.slot_id: placement}
        state = replace(state, placements={**state.placements, pair.doc_id: doc_placements})
        placed.append(pair)
    return state, tuple(placed)


def _preset_place(  # noqa: PLR0913 — входы одной пары
    point: RoutePoint,
    state: SignaturesState,
    pair: DocSlot,
    places: PackPlaces,
    origins: Collection[PlacementOrigin | None],
    src: SourceAnchors,
) -> SignaturePlacement | None:
    """Место пресета у пары или None, если пару не трогать (см. `apply_places`)."""
    doc = point.documents.get(pair.doc_id)
    runtime = point.runtime.get(pair.slot_id)
    if doc is None or runtime is None:
        return None
    if signed_over_frozen(state, pair.doc_id) or _shared_per_author(point, pair):
        return None
    existing = state.placements.get(pair.doc_id, {}).get(pair.slot_id)
    origin = places.info(pair.doc_id, pair.slot_id, existing).origin if existing is not None else None
    if origin not in origins:
        return None
    anchored = isinstance(runtime.slot_def.entry_for(doc.def_id), AnchorPlace)
    if anchored and existing is not None and not src.known:
        return None
    placement = pack_placement(runtime.slot_def, doc.def_id, existing, point.version.version, src)
    if placement is not None and mark_may_show(point, pair, state):
        placement = replace(placement, enabled=True)
    return placement


def apply_optional(
    point: RoutePoint,
    state: SignaturesState,
    pairs: Iterable[DocSlot],
    preset: RoutePreset,
    *,
    unset: bool,
    held: Collection[str] = (),
    signed: Callable[[DocSlot], bool] = lambda _pair: False,
    skip_docs: Collection[str] = (),
) -> tuple[SignaturesState, tuple[DocSlot, ...], tuple[DocSlot, ...]]:
    """Отметки «Подпись необязательна» пар маршрута по пресету: ставит, а с `unset` и снимает (15.5, 15.6).

    Правила те же, что у ручной отметки (13.3): слот, который пак запрещает (`required`), не отмечается; подписанный
    слот документа, который маршрут держит (`held`), тоже. Снятая отметка у пропущенной пары снимает и пропуск, если
    маршрут документ не держит (черновик, отменён); иначе пропуск остаётся до нового раунда. Документы `skip_docs`
    держит другой маршрут: их отметки не трогаются.
    """
    profile_id = point.profile.id
    marked: list[DocSlot] = []
    unmarked: list[DocSlot] = []
    for pair in dict.fromkeys(pairs):
        if pair.doc_id in skip_docs:
            continue
        runtime = point.runtime.get(pair.slot_id)
        on = state.is_optional(pair.doc_id, profile_id, pair.slot_id)
        if preset.marks_optional(pair):
            if on or runtime is None or runtime.required or (pair.doc_id in held and signed(pair)):
                continue
            state = with_optional(state, pair.doc_id, profile_id, pair.slot_id, True)
            marked.append(pair)
        elif unset and on:
            state = with_optional(state, pair.doc_id, profile_id, pair.slot_id, False)
            if pair.doc_id not in held and state.skip_of(pair.doc_id, pair.slot_id, profile_id) is not None:
                state = without_skip(state, pair.doc_id, pair.slot_id)
            unmarked.append(pair)
    return state, tuple(marked), tuple(unmarked)
