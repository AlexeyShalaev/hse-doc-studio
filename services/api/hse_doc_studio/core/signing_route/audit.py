"""Аудит маршрута подписания (docs/design/signing-route.md, раздел 6.7).

Журнал аудита получает записи `signing_route.*`. Большая часть выводится из событий истории маршрута
(`audit_of_event`): отправка, согласие, подпись, возврат, остановка, отмена, завершение, напоминание и повтор
приглашения. У черновика, правки, снятия с контроля и правок подписанта (способ, плашка, картинка) событий истории
нет, их записывают сценарии (`RouteAuditAction`).

В подробностях только идентификаторы и метаданные: маршрут, точка, раунд, шаг, персона, документы и слоты, причина.
Комментарий возврата остаётся в истории маршрута; содержимое файлов, пароли и ключи в аудит не попадают никогда.
Имена полей не содержат `key`, `token`, `secret`: такие поля журнал вычёркивает (`core.identity.redaction`).

`signing_route_scope` помечает действие как сделанное в маршруте: аудит подписей (`signature.freeze`,
`signature.sign`, `signature.attach`) дописывает к записи `route_id`.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from hse_doc_studio.core.signing_route.entities import EventKind, Participant, RouteEvent, SigningRoute, StopReason


class RouteAuditAction(StrEnum):
    """Действия журнала аудита `signing_route.*`."""

    create = "signing_route.create"
    update = "signing_route.update"
    send = "signing_route.send"
    cancel = "signing_route.cancel"
    archive = "signing_route.archive"
    approve = "signing_route.approve"
    sign = "signing_route.sign"
    return_ = "signing_route.return"
    pause = "signing_route.pause"
    complete = "signing_route.complete"
    remind = "signing_route.remind"
    invite = "signing_route.invite"
    signer_method = "signing_route.signer_method"
    signer_plate = "signing_route.signer_plate"
    signer_image = "signing_route.signer_image"


# Событие истории маршрута и его запись в журнале. `frozen` в журнале уже есть: `signature.freeze` с `route_id`
# на каждый документ. `resumed` никто не пишет: повторная отправка это событие `sent` нового раунда.
EVENT_ACTIONS: Mapping[EventKind, RouteAuditAction] = {
    EventKind.sent: RouteAuditAction.send,
    EventKind.approved: RouteAuditAction.approve,
    EventKind.signed: RouteAuditAction.sign,
    EventKind.returned: RouteAuditAction.return_,
    EventKind.paused: RouteAuditAction.pause,
    EventKind.cancelled: RouteAuditAction.cancel,
    EventKind.completed: RouteAuditAction.complete,
    EventKind.reminded: RouteAuditAction.remind,
    EventKind.invited: RouteAuditAction.invite,
}
UNAUDITED_EVENTS = frozenset({EventKind.frozen, EventKind.resumed})

# Что из подробностей события переходит в журнал. Комментария возврата (`comment`) здесь нет намеренно.
_EVENT_DETAILS = ("doc_id", "slot_id", "reason", "trigger", "delivery", "invitation_id")


@dataclass(frozen=True)
class RouteAuditRecord:
    """Запись журнала о маршруте: действие, кто (None у сервера) и подробности без проекта."""

    action: RouteAuditAction
    actor_id: UUID | None
    details: Mapping[str, object]


def route_details(route: SigningRoute, *, round: int | None = None) -> dict[str, object]:
    """Общее у всех записей: маршрут, точка сдачи и раунд."""
    return {
        "route_id": str(route.id),
        "profile_id": route.profile_id,
        "round": route.round if round is None else round,
    }


def participant_details(route: SigningRoute, participant: Participant) -> dict[str, object]:
    """Участник: его id в маршруте, персона, номер шага (с единицы) и аккаунт, если приглашение принято."""
    steps = {step: number for number, step in enumerate(route.steps, start=1)}
    details: dict[str, object] = {
        "participant_id": str(participant.id),
        "persona": participant.persona,
        "step": steps.get(participant.step, participant.step),
    }
    if participant.user_id is not None:
        details["user_id"] = participant.user_id.hex
    return details


def slots_details(participant: Participant) -> list[dict[str, str]]:
    return [{"doc_id": pair.doc_id, "slot_id": pair.slot_id} for pair in participant.assignments]


def record_of(
    action: RouteAuditAction,
    route: SigningRoute,
    *,
    actor_id: UUID | None,
    participant: Participant | None = None,
    details: Mapping[str, object] | None = None,
) -> RouteAuditRecord:
    """Запись сценария о действии без события истории (черновик, правка, снятие с контроля, правки подписанта)."""
    body = route_details(route)
    if participant is not None:
        body.update(participant_details(route, participant))
    body.update(details or {})
    return RouteAuditRecord(action, actor_id, body)


def audit_of_event(route: SigningRoute, event: RouteEvent) -> RouteAuditRecord | None:
    """Запись журнала о событии истории маршрута; None у событий, которых в журнале нет (`UNAUDITED_EVENTS`).

    `route` маршрут после перехода, которому принадлежит событие.
    """
    action = EVENT_ACTIONS.get(event.kind)
    if action is None:
        return None
    details = route_details(route, round=event.round)
    participant = _participant(route, event.participant_id)
    if participant is not None:
        details.update(participant_details(route, participant))
    details.update({name: event.details[name] for name in _EVENT_DETAILS if event.details.get(name) is not None})
    details.update(_kind_details(route, event, participant))
    return RouteAuditRecord(action, event.actor_id, details)


def _kind_details(route: SigningRoute, event: RouteEvent, participant: Participant | None) -> dict[str, object]:
    """Что запись добавляет по виду события: состав отправленного, слоты согласия, ушедший участник."""
    if event.kind is EventKind.sent:
        return {
            "docs": list(route.docs),
            "steps": len(route.steps),
            "participants": len(route.participants),
            "deadline": route.deadline.isoformat() if route.deadline is not None else None,
            "resend": event.round > 1,
        }
    if event.kind is EventKind.approved and participant is not None:
        return {"slots": slots_details(participant)}
    if event.kind is EventKind.completed:
        return {"docs": list(route.docs)}
    if event.kind is EventKind.paused and event.details.get("reason") == StopReason.participant_left.value:
        left = _participant(route, route.stopped_by)
        return participant_details(route, left) if left is not None else {}
    return {}


def _participant(route: SigningRoute, participant_id: UUID | None) -> Participant | None:
    return next((p for p in route.participants if p.id == participant_id), None)


# --- подписи, сделанные в маршруте ----------------------------------------------------------------------------------

_scope: contextvars.ContextVar[UUID | None] = contextvars.ContextVar("signing_route_scope", default=None)


@contextmanager
def signing_route_scope(route_id: UUID | None) -> Iterator[None]:
    """Действия с подписями внутри блока сделаны маршрутом или его участником в свою очередь.

    None ничего не меняет: слот вне маршрута подписывается как обычно.
    """
    if route_id is None:
        yield
        return
    token = _scope.set(route_id)
    try:
        yield
    finally:
        _scope.reset(token)


def current_signing_route() -> UUID | None:
    """Маршрут, в котором идёт текущее действие с подписями; None вне маршрута."""
    return _scope.get()
