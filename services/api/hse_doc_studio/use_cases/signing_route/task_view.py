"""Задача подписанта: то, что видит участник на странице `/sign/...` (docs/design/signing-route.md, 3.2, 7 и 8.2).

Только своё: документы, где у участника есть слоты (у согласующего без слотов все документы маршрута), места слотов,
люди маршрута и их состояния, события. Чтение ничего не пишет и показывает вычисленное состояние (раздел 5.5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from hse_doc_studio.core.signatures.plan import (
    CRYPTO_METHODS,
    PlanReason,
    SignMethod,
    SlotStatus,
    VisibleMark,
    mark_of,
    method_of,
    slot_state,
)
from hse_doc_studio.core.signatures.ports import IMarkMeasure
from hse_doc_studio.core.signatures.stamps import date_mark_text, stamps_for_doc
from hse_doc_studio.core.signing_route.engine import Evaluation, ParticipantView, RouteFacts, approval_token
from hse_doc_studio.core.signing_route.entities import (
    DocSlot,
    EventKind,
    Participant,
    ParticipantState,
    RouteEvent,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
)
from hse_doc_studio.core.signing_route.signer import (
    available_methods,
    current_method,
    image_ready,
    known_plate,
    task_tokens,
)
from hse_doc_studio.core.value_objects import SignaturePlacement, SignaturesState, SignerInfo
from hse_doc_studio.use_cases.signing_route.key_signer import KeyInfo
from hse_doc_studio.use_cases.signing_route.point import RoutePoint
from hse_doc_studio.use_cases.signing_route.views import (
    EventView,
    People,
    card_name,
    displayed,
    doc_changed,
    event_view,
    sent_version,
)

# Пропорция рамки под картинку, которой ещё нет: как у метки без известных размеров (`stamps._DEFAULT_ASPECT`).
_IMAGE_ASPECT = 0.4
_ACTED = frozenset({EventKind.approved, EventKind.signed, EventKind.returned})


@dataclass(frozen=True)
class TaskDate:
    """Метка даты слота на документе (14.7): место рамки и что напечатано сейчас (None: метка пустая)."""

    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    text: str | None


@dataclass(frozen=True)
class TaskSlot:
    """Слот на документе: место метки на странице, что на ней будет и статус слота по плану подписей.

    `height_mm` высота метки (None у слота без видимой метки): у картинки по её пропорциям, у плашки по вёрстке.
    """

    slot_id: str
    label: dict[str, str]
    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float | None
    mark: VisibleMark
    status: SlotStatus
    reason: PlanReason | None
    # Подпись необязательна на точке маршрута (13.3).
    optional: bool = False
    # Метки даты слота на этом документе (14.7).
    dates: tuple[TaskDate, ...] = ()


@dataclass(frozen=True)
class TaskDoc:
    doc_id: str
    name: dict[str, str]
    frozen: bool
    # Отпечаток для `expected` следующего действия участника; None, когда действовать нечего.
    token: str | None
    mine: tuple[TaskSlot, ...]
    others: tuple[TaskSlot, ...]
    # Дата версии на подписи (12.9); None, если её нет.
    sent_at: datetime | None = None
    # Документ изменился с прошлого согласия участника: согласовать заново.
    changed_since_mine: bool = False
    # Рабочая сборка ушла от версии на подписи; только автору и управляющим маршрутом, остальным None.
    changed: bool | None = None


@dataclass(frozen=True)
class TaskPerson:
    name: str | None
    persona: str
    state: ParticipantState
    # Последнее действие участника в этом раунде: согласие, подпись или возврат.
    at: datetime | None
    me: bool
    # Имя персоны по карточке проекта; его согласие ещё меняет видимый слой (до него PDF не зафиксируют).
    card_name: str | None = None
    changes_visible: bool = False


@dataclass(frozen=True)
class TaskKeys:
    """Ключи Студии подписанта: разрешены ли они на установке и его ключ по умолчанию (None, если нет или запрет)."""

    server_keys_allowed: bool
    default_key: KeyInfo | None


@dataclass(frozen=True)
class TaskDetails:
    route: SigningRoute
    project_name: str
    profile_name: dict[str, str]
    status: RouteStatus
    phase: RoutePhase | None
    stop_reason: StopReason | None
    current_step: int | None
    sender_name: str | None
    steps: tuple[tuple[TaskPerson, ...], ...]
    participant: Participant
    view: ParticipantView
    methods: tuple[SignMethod, ...]
    method: SignMethod | None
    image_ready: bool
    plate: SignerInfo | None
    keys: TaskKeys
    docs: tuple[TaskDoc, ...]
    events: tuple[EventView, ...]
    # Раунд новой версии, в котором изменился хотя бы один документ участника (12.6).
    new_version: bool = False

    @property
    def optional(self) -> bool:
        """Все оставшиеся пары участника необязательны на точке (13.6): остались неподписанные и непропущенные, и
        среди них нет обязательных."""
        remaining = [
            slot for doc in self.docs for slot in doc.mine if slot.status not in (SlotStatus.signed, SlotStatus.skipped)
        ]
        return bool(remaining) and all(slot.optional for slot in remaining)


def build_task(  # noqa: PLR0913 — входы одного ответа
    point: RoutePoint,
    route: SigningRoute,
    facts: RouteFacts,
    evaluation: Evaluation,
    me: Participant,
    people: People,
    events: Sequence[RouteEvent],
    keys: TaskKeys,
    measure: IMarkMeasure,
    *,
    manages: bool = False,
) -> TaskDetails:
    """Задача участника `me`. `manages` вправе ли смотрящий управлять маршрутом: только ему видно, что рабочая
    сборка ушла от версии на подписи (12.9), подписант рабочих правок не видит."""
    status, phase, stop = displayed(route, evaluation)
    view = evaluation.participant(me.id)
    positions = {step: i for i, step in enumerate(route.steps, start=1)}
    acted = _last_actions(route, events)
    steps = tuple(
        tuple(
            TaskPerson(
                name=people.name(p),
                persona=p.persona,
                state=evaluation.participant(p.id).state,
                at=acted.get(p.id),
                me=p.id == me.id,
                card_name=card_name(point.project, p.persona),
                changes_visible=evaluation.participant(p.id).changes_visible,
            )
            for p in route.participants
            if positions[p.step] == number
        )
        for number in positions.values()
    )
    mine = [pair for pair in me.assignments if pair in point.allowed]
    return TaskDetails(
        route=route,
        project_name=point.project.name,
        profile_name=dict(point.profile.name),
        status=status,
        phase=phase,
        stop_reason=stop,
        current_step=evaluation.step_position if status is RouteStatus.active else None,
        sender_name=people.names.get(route.sent_by) if route.sent_by is not None else None,
        steps=steps,
        participant=me,
        view=view,
        methods=available_methods(me, view, facts.state, point.methods(mine), server_keys=keys.server_keys_allowed),
        method=current_method(me, facts.state),
        image_ready=image_ready(me, facts),
        plate=known_plate(me, facts),
        keys=keys,
        docs=_docs(point, route, facts, me, view, measure, manages=manages),
        events=tuple(event_view(e, people, show_comments=True) for e in events),
        new_version=bool(set(route.round_changed_docs) & set(me.doc_ids(route.docs))),
    )


def _last_actions(route: SigningRoute, events: Sequence[RouteEvent]) -> dict[UUID, datetime]:
    """Время последнего действия каждого участника в текущем раунде: по событиям, иначе по согласию."""
    acted: dict[UUID, datetime] = {
        p.id: p.approval.at for p in route.participants if p.approval is not None and p.approval.round == route.round
    }
    for event in events:
        if event.round != route.round or event.kind not in _ACTED or event.participant_id is None:
            continue
        previous = acted.get(event.participant_id)
        if previous is None or event.at > previous:
            acted[event.participant_id] = event.at
    return acted


def _docs(  # noqa: PLR0913 — входы одного списка
    point: RoutePoint,
    route: SigningRoute,
    facts: RouteFacts,
    me: Participant,
    view: ParticipantView,
    measure: IMarkMeasure,
    *,
    manages: bool,
) -> tuple[TaskDoc, ...]:
    tokens = task_tokens(route, me, view, facts)
    owned = {pair for p in route.participants for pair in p.assignments}
    pairs = list(dict.fromkeys([*point.required, *owned]))
    result: list[TaskDoc] = []
    for doc_id in me.doc_ids(route.docs):
        doc_pairs = [pair for pair in pairs if pair.doc_id == doc_id]
        uses_frozen = any(
            method_of(slot.sign_mode) in CRYPTO_METHODS
            for pair in doc_pairs
            if (slot := facts.state.slots.get(pair.slot_id)) is not None
        )
        slots = {
            pair: _slot(point, route.profile_id, facts, pair, measure, uses_frozen=uses_frozen) for pair in doc_pairs
        }
        sent = sent_version(route, facts.state, doc_id)
        result.append(
            TaskDoc(
                doc_id=doc_id,
                name=point.doc_name(doc_id),
                frozen=doc_id in facts.state.frozen,
                token=tokens.get(doc_id),
                mine=tuple(slot for pair, slot in slots.items() if pair in me.assignments),
                others=tuple(slot for pair, slot in slots.items() if pair not in me.assignments),
                sent_at=sent.at if sent is not None else None,
                changed_since_mine=_changed_since(me, facts, doc_id),
                changed=doc_changed(route, facts, doc_id, sent) if manages else None,
            )
        )
    return tuple(result)


def _changed_since(me: Participant, facts: RouteFacts, doc_id: str) -> bool:
    """Документ изменился с прошлого согласия участника: отпечаток его согласия другой (12.6)."""
    approval = me.approval
    if approval is None or doc_id not in approval.tokens:
        return False
    return approval.tokens[doc_id] != approval_token(facts.doc(doc_id))


def _slot(  # noqa: PLR0913 — входы одного слота
    point: RoutePoint, profile_id: str, facts: RouteFacts, pair: DocSlot, measure: IMarkMeasure, *, uses_frozen: bool
) -> TaskSlot:
    state = facts.state
    plan = slot_state(
        state,
        pair.doc_id,
        pair.slot_id,
        facts.doc(pair.doc_id),
        allowed=point.allowed.get(pair, ()),
        uses_frozen=uses_frozen,
        profile_id=profile_id,
    )
    placement = _placement(point, state.placements, pair)
    mark = mark_of(state.slots.get(pair.slot_id))
    return TaskSlot(
        slot_id=pair.slot_id,
        label=point.slot_label(pair.slot_id),
        page=placement.page,
        x_mm=placement.x_mm,
        y_mm=placement.y_mm,
        width_mm=placement.width_mm,
        height_mm=_height(point, state, pair, placement, mark, measure),
        mark=mark,
        status=plan.status,
        reason=plan.reason,
        optional=facts.is_optional(pair),
        dates=tuple(
            TaskDate(
                page=mark.page,
                x_mm=mark.x_mm,
                y_mm=mark.y_mm,
                width_mm=mark.width_mm,
                height_mm=mark.height_mm,
                text=date_mark_text(state, pair.doc_id, pair.slot_id, mark, str(point.project.lang)),
            )
            for mark in placement.dates
        ),
    )


def _placement(
    point: RoutePoint, placements: Mapping[str, Mapping[str, SignaturePlacement]], pair: DocSlot
) -> SignaturePlacement:
    """Размещение слота на документе; пока автор его не задал, место из пака для документа (signing-route.md, 15.3)."""
    found = placements.get(pair.doc_id, {}).get(pair.slot_id)
    if found is not None:
        return found
    slot = point.runtime.get(pair.slot_id)
    if slot is None:
        return SignaturePlacement(enabled=False, page=1, x_mm=0.0, y_mm=0.0, width_mm=0.0)
    doc = point.documents.get(pair.doc_id)
    default = slot.slot_def.place_for(doc.def_id) if doc is not None else slot.slot_def.default_placement
    return SignaturePlacement(
        enabled=False, page=default.page, x_mm=default.x_mm, y_mm=default.y_mm, width_mm=default.width_mm
    )


def _height(  # noqa: PLR0913 — входы одной метки
    point: RoutePoint,
    state: SignaturesState,
    pair: DocSlot,
    placement: SignaturePlacement,
    mark: VisibleMark,
    measure: IMarkMeasure,
) -> float | None:
    """Высота метки, которую поставит маршрут: та же метка, что у фиксации, но без учёта придержания."""
    if mark is VisibleMark.none:
        return None
    shown = replace(state, withheld={}, placements={pair.doc_id: {pair.slot_id: replace(placement, enabled=True)}})
    project = point.project
    stamps = stamps_for_doc(shown, pair.doc_id, project.folder, str(project.lang), png_exists=lambda _path: True)
    # Метки даты слота (14.3) идут после его метки и высоту места подписи не задают.
    marks = [stamp for stamp in stamps if not stamp.is_date]
    if marks:
        return round(measure.mark_height_mm(marks[0]), 2)
    return round(placement.width_mm * _IMAGE_ASPECT, 2)
