"""Ход маршрута для автора: шаги с людьми, документы со слотами, события (docs/design/signing-route.md, 8.2).

Чтение ничего не пишет, но показывает вычисленное состояние (раздел 5.5): статус, фаза и причина остановки берутся
из расчёта, даже если хук изменения документа ещё не сработал.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import SignMode
from hse_doc_studio.core.signatures.plan import (
    AUTHOR_PERSONA,
    CRYPTO_METHODS,
    PlanReason,
    SignMethod,
    SlotStatus,
    method_of,
    slot_state,
)
from hse_doc_studio.core.signing_route.engine import Evaluation, ParticipantView, RouteFacts, approval_token
from hse_doc_studio.core.signing_route.entities import (
    TURN_STATES,
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
from hse_doc_studio.core.signing_route.ports import RouteCandidate, RouteInvitee
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.use_cases.signing_route.point import RoutePoint


class Membership(StrEnum):
    """Человек участника в проекте: участник с персоной шага, приглашение отправлено, нет в проекте."""

    member = "member"
    invited = "invited"
    missing = "missing"


@dataclass(frozen=True)
class People:
    """Что известно о людях маршрута: имена, ожидающие приглашения, персоны в проекте."""

    names: Mapping[UUID, str]
    invitees: Mapping[str, RouteInvitee]
    personas: Mapping[UUID, frozenset[str]]

    def membership(self, p: Participant) -> Membership:
        if p.user_id is not None:
            return Membership.member if p.persona in self.personas.get(p.user_id, ()) else Membership.missing
        if p.invitation_id is not None and p.invitation_id in self.invitees:
            return Membership.invited
        return Membership.missing

    def name(self, p: Participant) -> str | None:
        """Имя участника; у приглашённого подсказка; чужого человека не называем, пока он не действовал в маршруте."""
        membership = self.membership(p)
        if p.user_id is not None and (membership is Membership.member or p.approval is not None):
            return self.names.get(p.user_id)
        if membership is Membership.invited and p.invitation_id is not None:
            return self.invitees[p.invitation_id].name
        return None


def card_name(project: Project, persona: str) -> str | None:
    """Имя человека персоны из карточки проекта («Научный руководитель: ФИО»); None, если его там нет.

    Приглашённого Студия знает только по маске почты, а автор маршрута знает его по карточке проекта: это имя и
    показывается рядом с маской, чтобы человек не оставался безымянным адресом.
    """
    person = {
        "supervisor": project.supervisor,
        "co_supervisor": project.co_supervisor,
        "academic_supervisor": project.academic_supervisor,
    }.get(persona)
    if person is not None:
        return person.name or None
    if persona == AUTHOR_PERSONA:
        return (project.authors[0].name or None) if project.authors else None
    author = next((a for a in project.authors if a.slug == persona), None)
    return (author.name or None) if author is not None else None


@dataclass(frozen=True)
class PersonView:
    participant: Participant
    step: int  # номер шага по порядку, с 1
    name: str | None
    # Имя персоны по карточке проекта: у приглашённого, кроме маски почты, только оно и известно.
    card_name: str | None
    membership: Membership
    method: SignMethod | None
    view: ParticipantView


@dataclass(frozen=True)
class SlotView:
    slot_id: str
    label: dict[str, str]
    participant_id: UUID | None
    # Слот добавлен к маршруту сверх точки: точка его не требует (6.5). Подпись на нём всё равно обязательна.
    extra: bool
    # Подпись необязательна на точке маршрута: автора можно пропустить (13.3).
    optional: bool
    status: SlotStatus
    reason: PlanReason | None


@dataclass(frozen=True)
class SentVersion:
    """Версия на подписи документа маршрута (`RouteDoc.sent`, 12.9): sha256, когда снята и каким раундом."""

    sha256: str
    at: datetime
    round: int


@dataclass(frozen=True)
class DocView:
    doc_id: str
    name: dict[str, str]
    built: bool
    frozen: bool
    # Отпечаток для `expected` отправки (`build:<sha>`); None, пока документ не собран.
    token: str | None
    slots: tuple[SlotView, ...]
    # Версия на подписи этого маршрута; None у черновика, после отмены и у маршрута без неё (12.9).
    sent: SentVersion | None = None
    # Рабочая сборка ушла от версии на подписи: есть что отправить новой версией.
    changed: bool = False


@dataclass(frozen=True)
class EventView:
    event: RouteEvent
    who: str | None
    comment: str | None
    reason: StopReason | None
    # Только у `sent` новой версии: документы, у которых сменилась версия на подписи (12.9).
    changed_docs: tuple[str, ...] | None = None


@dataclass(frozen=True)
class PersonOption:
    """Кого можно поставить на персону: участник проекта (`member`, id это `users.id`) или приглашение."""

    kind: str  # "member" | "invitation"
    id: str
    name: str | None


@dataclass(frozen=True)
class PersonaCandidates:
    persona: str
    people: tuple[PersonOption, ...]


def persona_candidates(
    personas: Sequence[str], candidates: Sequence[RouteCandidate], invitees: Sequence[RouteInvitee]
) -> tuple[PersonaCandidates, ...]:
    """По каждой персоне участники проекта с ней, затем ожидающие приглашения с ней (раздел 6.5)."""
    return tuple(
        PersonaCandidates(
            persona=persona,
            people=(
                *(PersonOption("member", c.user_id.hex, c.name) for c in candidates if c.persona == persona),
                *(PersonOption("invitation", i.invitation_id, i.name) for i in invitees if i.persona == persona),
            ),
        )
        for persona in dict.fromkeys(personas)
    )


@dataclass(frozen=True)
class RouteDetails:
    route: SigningRoute
    profile_name: dict[str, str]
    status: RouteStatus
    phase: RoutePhase | None
    stop_reason: StopReason | None
    current_step: int | None
    sent_by_name: str | None
    docs: tuple[DocView, ...]
    steps: tuple[tuple[PersonView, ...], ...]
    events: tuple[EventView, ...]
    # Из кого выбирать на персоны маршрута и его слотов; только тому, кто управляет маршрутом.
    candidates: tuple[PersonaCandidates, ...] = ()
    # Читатель управляет маршрутом (`SUBMISSION_CREATE`): только ему показывается `skip` участников (13.6).
    manages: bool = False

    @property
    def people(self) -> tuple[PersonView, ...]:
        return tuple(person for step in self.steps for person in step)

    @property
    def changed_docs(self) -> tuple[str, ...]:
        """Документы с изменениями после отправки, в порядке маршрута (`SigningRoute.changed_docs`)."""
        return tuple(doc.doc_id for doc in self.docs if doc.changed)

    @property
    def waiting_for(self) -> tuple[PersonView, ...]:
        """Чья очередь сейчас: кто должен действовать и приглашённые текущего шага."""
        if self.status is not RouteStatus.active:
            return ()
        return tuple(
            person
            for person in self.people
            if person.view.state in TURN_STATES
            or (person.view.state is ParticipantState.invited and person.step == self.current_step)
        )


# Версии на подписи у черновика нет, а отмена её снимает (12.4): такой маршрут ничего не показывает.
_UNSENT = frozenset({RouteStatus.draft, RouteStatus.cancelled})


def sent_version(route: SigningRoute, state: SignaturesState, doc_id: str) -> SentVersion | None:
    """Версия на подписи документа, которую снял этот маршрут; None у черновика, отменённого и без версии.

    Версия чужого маршрута (прежнего маршрута точки, снятого с контроля) этому маршруту не принадлежит.
    """
    if route.status in _UNSENT:
        return None
    pinned = state.pinned.get(doc_id)
    if pinned is None or pinned.route_id != str(route.id):
        return None
    try:
        at = datetime.fromisoformat(pinned.pinned_at)
    except ValueError:
        fallback = route.doc_sent_at(doc_id)
        if fallback is None:
            return None
        at = fallback
    return SentVersion(sha256=pinned.sha256, at=at, round=pinned.round)


def doc_changed(route: SigningRoute, facts: RouteFacts, doc_id: str, sent: SentVersion | None) -> bool:
    """Рабочая сборка есть и отличается от версии на подписи, а без неё (маршрут 0.20.0, перенос не удался) от
    отпечатка снимка (12.9). Несобранные правки не считаются; у черновика и отменённого всегда False."""
    if route.status in _UNSENT:
        return False
    working = facts.doc(doc_id).working_sha256
    if working is None:
        return False
    if sent is not None:
        return working != sent.sha256
    seen = route.snapshot.get(doc_id)
    return seen is not None and seen.compiled_sha256 is not None and seen.compiled_sha256 != working


def method_of_participant(p: Participant, facts: RouteFacts) -> SignMethod | None:
    """Способ слотов участника (первого слота); None у согласующего без слотов."""
    if not p.assignments:
        return None
    slot = facts.state.slots.get(p.assignments[0].slot_id)
    return method_of(slot.sign_mode if slot is not None else SignMode.image)


def displayed(route: SigningRoute, evaluation: Evaluation) -> tuple[RouteStatus, RoutePhase | None, StopReason | None]:
    """Статус, фаза и причина остановки, как их видит человек: по расчёту, а не по последней записи."""
    status = evaluation.status
    stop = evaluation.stop
    if stop is None and status in (RouteStatus.paused, RouteStatus.returned):
        stop = route.stop_reason
    return status, evaluation.phase, stop


def build_details(
    point: RoutePoint,
    route: SigningRoute,
    facts: RouteFacts,
    evaluation: Evaluation,
    people: People,
    events: Sequence[RouteEvent] = (),
    *,
    show_comments: bool = False,
) -> RouteDetails:
    status, phase, stop = displayed(route, evaluation)
    positions = {step: i for i, step in enumerate(route.steps, start=1)}
    persons = [
        PersonView(
            participant=p,
            step=positions[p.step],
            name=people.name(p),
            card_name=card_name(point.project, p.persona),
            membership=people.membership(p),
            method=method_of_participant(p, facts),
            view=evaluation.participant(p.id),
        )
        for p in route.participants
    ]
    steps = tuple(tuple(person for person in persons if person.step == number) for number in positions.values())
    return RouteDetails(
        route=route,
        profile_name=dict(point.profile.name),
        status=status,
        phase=phase,
        stop_reason=stop,
        current_step=evaluation.step_position if status is RouteStatus.active else None,
        sent_by_name=people.names.get(route.sent_by) if route.sent_by is not None else None,
        docs=doc_views(point, route, facts),
        steps=steps,
        events=tuple(event_view(e, people, show_comments=show_comments) for e in events),
    )


def doc_views(point: RoutePoint, route: SigningRoute, facts: RouteFacts) -> tuple[DocView, ...]:
    """Документы маршрута: пары точки и включённые автором необязательные, с участником и статусом."""
    owners = {pair: p.id for p in route.participants for pair in p.assignments}
    pairs = list(dict.fromkeys([*point.required, *owners]))
    result: list[DocView] = []
    for doc_id in route.docs:
        doc_pairs = [pair for pair in pairs if pair.doc_id == doc_id]
        doc_facts = facts.doc(doc_id)
        built = doc_facts.compiled_sha256 is not None
        sent = sent_version(route, facts.state, doc_id)
        result.append(
            DocView(
                doc_id=doc_id,
                name=point.doc_name(doc_id),
                built=built,
                frozen=doc_id in facts.state.frozen,
                token=approval_token(doc_facts) if built else None,
                slots=_slots(point, route.profile_id, facts, doc_pairs, owners),
                sent=sent,
                changed=doc_changed(route, facts, doc_id, sent),
            )
        )
    return tuple(result)


def _slots(
    point: RoutePoint, profile_id: str, facts: RouteFacts, pairs: Collection[DocSlot], owners: Mapping[DocSlot, UUID]
) -> tuple[SlotView, ...]:
    uses_frozen = any(
        method_of(slot.sign_mode) in CRYPTO_METHODS
        for pair in pairs
        if (slot := facts.state.slots.get(pair.slot_id)) is not None
    )
    views: list[SlotView] = []
    for pair in pairs:
        state = slot_state(
            facts.state,
            pair.doc_id,
            pair.slot_id,
            facts.doc(pair.doc_id),
            allowed=point.allowed.get(pair, ()),
            uses_frozen=uses_frozen,
            profile_id=profile_id,
        )
        views.append(
            SlotView(
                slot_id=pair.slot_id,
                label=point.slot_label(pair.slot_id),
                participant_id=owners.get(pair),
                extra=pair not in point.allowed,
                optional=pair.slot_id in facts.optional.get(pair.doc_id, ()),
                status=state.status,
                reason=state.reason,
            )
        )
    return tuple(views)


def event_view(event: RouteEvent, people: People, *, show_comments: bool) -> EventView:
    raw_comment = event.details.get("comment")
    raw_reason = event.details.get("reason")
    reason = StopReason(raw_reason) if isinstance(raw_reason, str) and raw_reason in StopReason else None
    return EventView(
        event=event,
        who=people.names.get(event.actor_id) if event.actor_id is not None else None,
        comment=raw_comment if show_comments and isinstance(raw_comment, str) else None,
        reason=reason,
        changed_docs=_changed_docs(event),
    )


def _changed_docs(event: RouteEvent) -> tuple[str, ...] | None:
    """`details.changed` события `sent` новой версии (12.6); None у остальных событий и у первой отправки."""
    if event.kind is not EventKind.sent or event.details.get("new_version") is not True:
        return None
    raw = event.details.get("changed")
    return tuple(item for item in raw if isinstance(item, str)) if isinstance(raw, list | tuple) else ()
