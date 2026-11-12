"""Маршруты подписания для тестов хранилища и сценариев: простой черновик и маршрут со всеми полями."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from hse_doc_studio.core.signing_route.entities import (
    Approval,
    DocSlot,
    DocSnapshot,
    EventKind,
    Notified,
    Participant,
    ParticipantSkip,
    RequestOutcome,
    RouteEvent,
    RoutePhase,
    RouteStatus,
    SigningRoute,
    StopReason,
)

DOC = "topic_application"
DOC2 = "application"
PROFILE = "topic-approval"
T0 = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def make_participant(
    step: int, persona: str, slots: Iterable[str] = (), *, docs: Iterable[str] = (DOC,), **changes: Any
) -> Participant:
    """Участник с пользователем; `slots` его слоты на каждом из `docs`."""
    pairs = tuple(DocSlot(doc_id, slot_id) for doc_id in docs for slot_id in slots)
    participant = Participant(id=uuid4(), step=step, persona=persona, user_id=uuid4(), assignments=pairs)
    return replace(participant, **changes)


def make_route(
    project_id: UUID,
    *,
    profile_id: str = PROFILE,
    docs: tuple[str, ...] = (DOC,),
    participants: Iterable[Participant] | None = None,
    **changes: Any,
) -> SigningRoute:
    """Черновик точки: автор, научрук и академрук по шагу, слоты на всех документах."""
    people = (
        tuple(participants)
        if participants is not None
        else (
            make_participant(1, "author", ["author"], docs=docs),
            make_participant(2, "supervisor", ["supervisor"], docs=docs),
            make_participant(3, "academic_supervisor", ["academic_supervisor"], docs=docs),
        )
    )
    route = SigningRoute(
        id=uuid4(), project_id=project_id, profile_id=profile_id, created_by=uuid4(), docs=docs, participants=people
    )
    return replace(route, **changes)


def make_full_route(project_id: UUID, *, profile_id: str = PROFILE) -> SigningRoute:
    """Идущий маршрут, где заполнено всё, что маршрут хранит.

    Документы и отпечатки согласия нарочно не по алфавиту и в разном порядке; параллельный шаг с согласующим без
    слотов; приглашённый без пользователя; согласия до и после фиксации; запросы, напоминания, срок, сообщение.
    """
    build = "b" * 64
    author = make_participant(
        1,
        "author",
        docs=(),
        assignments=(DocSlot(DOC, "author"), DocSlot(DOC2, "author")),
        approval=Approval(round=3, tokens={DOC: f"build:{build}", DOC2: "build:"}, at=T0),
        notified=Notified(round=3, outcome=RequestOutcome.sign, at=T0 + timedelta(minutes=1)),
        reminded_at=T0 + timedelta(hours=2, microseconds=5),
        reminders=2,
    )
    supervisor = make_participant(
        2,
        "supervisor",
        ["supervisor"],
        docs=(DOC2,),
        approval=Approval(round=3, tokens={DOC2: "build:"}, at=T0 + timedelta(minutes=5), phase=RoutePhase.signing),
        notified=Notified(round=3, outcome=RequestOutcome.approve_sign, at=T0 + timedelta(minutes=2)),
    )
    approver = make_participant(
        2,
        "co_supervisor",
        notified=Notified(round=2, outcome=RequestOutcome.approve, at=T0 - timedelta(days=1)),
    )
    invited = make_participant(
        3,
        "academic_supervisor",
        ["academic_supervisor"],
        docs=(DOC2,),
        user_id=None,
        invitation_id=f"inv_{uuid4().hex}",
        # Автор пропустил приглашённого (13.3): раунд, время, пары, метка осталась в одном документе.
        skipped=ParticipantSkip(
            round=3,
            at=T0 + timedelta(hours=3, microseconds=7),
            by=uuid4(),
            pairs=(DocSlot(DOC2, "academic_supervisor"),),
            kept_marks=(DOC2,),
            refrozen=(DOC,),
        ),
    )
    return make_route(
        project_id,
        profile_id=profile_id,
        docs=(DOC2, DOC),
        participants=(author, supervisor, approver, invited),
        status=RouteStatus.active,
        phase=RoutePhase.signing,
        round=3,
        snapshot={
            DOC2: DocSnapshot(compiled_sha256="a" * 64, marks_digest="m" * 64, frozen_sha256="f" * 64),
            DOC: DocSnapshot(compiled_sha256=None, marks_digest=""),
        },
        deadline=T0 + timedelta(days=5),
        message="Подпишите, пожалуйста: «тема согласована»",
        sent_by=author.user_id,
        sent_at=T0,
    )


def make_event(route: SigningRoute, kind: EventKind = EventKind.sent, **changes: Any) -> RouteEvent:
    event = RouteEvent(route_id=route.id, round=route.round, at=T0, kind=kind, actor_id=route.created_by)
    return replace(event, **changes)


def stopped(route: SigningRoute, by: Participant, reason: StopReason = StopReason.returned) -> SigningRoute:
    """Остановленный маршрут: возврат или уход участника."""
    status = RouteStatus.returned if reason is StopReason.returned else RouteStatus.paused
    return replace(route, status=status, phase=None, stop_reason=reason, stopped_by=by.id)
