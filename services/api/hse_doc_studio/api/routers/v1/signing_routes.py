"""Маршрут подписания глазами автора (docs/design/signing-route.md, раздел 8): черновик, правка, ход, предпросмотр,
отправка, отмена, снятие с контроля, «Напомнить».

Только сервер: локальная Студия отвечает 404 (раздел 6.9). Права по таблице `ROUTE_ACTIONS`: чтение `OUTPUT_READ`,
управление `SUBMISSION_CREATE`. Гостю и ссылочному праву ход маршрута не раскрывается (404, раздел 7).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, NoReturn, cast
from uuid import UUID

from dishka.integrations.fastapi import FromDishka
from fastapi import APIRouter, Depends, Query, Response, status

from hse_doc_studio.api import invitation_views as people_views
from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.dishka_route import SafeDishkaRoute
from hse_doc_studio.api.schemas import signing_route as s
from hse_doc_studio.api.signing_route_errors import SigningKeyError, blocker_body
from hse_doc_studio.core.access.checker import ProjectForbiddenError
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.signatures.key_policy import SigningKeyStorageDeniedError
from hse_doc_studio.core.signing_route.drafting import PersonDraft
from hse_doc_studio.core.signing_route.entities import DocSlot, RouteConflictError, RouteInputError
from hse_doc_studio.use_cases.signatures._studio_signer import KeyPassphraseRequiredError
from hse_doc_studio.use_cases.signing_route.author import (
    RoutePreview,
    RouteSummary,
    RouteUpdate,
    SendRequest,
    SigningRouteControl,
    SigningRouteDrafts,
    SigningRouteSending,
)
from hse_doc_studio.use_cases.signing_route.key_signer import (
    KeyInfo,
    KeyNotFoundError,
    KeyPassphraseInvalidError,
    KeyRequest,
)
from hse_doc_studio.use_cases.signing_route.reminders import SigningRouteReminding
from hse_doc_studio.use_cases.signing_route.views import EventView, PersonView, RouteDetails

router = APIRouter(route_class=SafeDishkaRoute, dependencies=[Depends(require_server_mode)])

_BASE = "/projects/{project_id}/signing-routes"


def _not_found() -> NotFoundError:
    return NotFoundError(localized_error("Маршрут подписания не найден", "Signing route not found"))


def reader() -> Actor:
    """Вошедший участник проекта: гостю и тому, кто открыл проект по ссылке, маршрута нет (404)."""
    actor = people_views.require_user()
    if actor.is_guest or actor.link_id is not None:
        raise _not_found()
    return actor


def _uuid(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise RouteInputError(
            "bad_id", localized_error(f"Неверный идентификатор {value!r}", f"Invalid identifier {value!r}")
        ) from None


# --- ответы ---------------------------------------------------------------------------------------------------------


def _iso_user(value: UUID | None) -> str | None:
    return value.hex if value is not None else None


def _written(created_at: datetime | None, updated_at: datetime | None) -> tuple[datetime, datetime]:
    """Время записи маршрута: у маршрута из хранилища оно есть всегда."""
    created = created_at or updated_at
    if created is None:
        raise _not_found()
    return created, updated_at or created


def route_response(details: RouteDetails) -> s.SigningRouteResponse:
    route = details.route
    created, updated = _written(route.created_at, route.updated_at)
    return s.SigningRouteResponse(
        id=str(route.id),
        project_id=str(route.project_id),
        profile=s.SigningProfileRef(id=route.profile_id, name=details.profile_name),
        status=details.status.value,
        phase=details.phase.value if details.phase is not None else None,
        round=route.round,
        current_step=details.current_step,
        deadline=route.deadline,
        message=route.message,
        stop_reason=details.stop_reason.value if details.stop_reason is not None else None,
        sent_by=(
            s.SigningPersonRef(id=route.sent_by.hex, name=details.sent_by_name or "")
            if route.sent_by is not None
            else None
        ),
        sent_at=route.sent_at,
        completed_at=route.completed_at,
        created_at=created,
        updated_at=updated,
        docs=[
            s.RouteDoc(
                doc_id=doc.doc_id,
                name=doc.name,
                frozen=doc.frozen,
                slots=[
                    s.RouteDocSlot(
                        slot_id=slot.slot_id,
                        label=slot.label,
                        participant_id=str(slot.participant_id) if slot.participant_id is not None else None,
                        optional=slot.optional,
                        status=slot.status.value,
                    )
                    for slot in doc.slots
                ],
            )
            for doc in details.docs
        ],
        steps=[[_participant(details, person) for person in step] for step in details.steps],
        events=[event_response(e) for e in details.events],
        candidates=[
            s.RoutePersonaCandidates(
                persona=group.persona,
                people=[
                    s.RoutePersonOption(kind=cast(Literal["member", "invitation"], o.kind), id=o.id, name=o.name)
                    for o in group.people
                ],
            )
            for group in details.candidates
        ],
    )


def event_response(e: EventView) -> s.RouteEvent:
    event = e.event
    return s.RouteEvent(
        id=str(event.id),
        kind=event.kind.value,
        round=event.round,
        at=event.at,
        who=e.who,
        participant_id=str(event.participant_id) if event.participant_id is not None else None,
        comment=e.comment,
        reason=e.reason.value if e.reason is not None else None,
    )


def _participant(details: RouteDetails, person: PersonView) -> s.RouteParticipant:
    p = person.participant
    approval = p.approval if p.approval is not None and p.approval.round == details.route.round else None
    return s.RouteParticipant(
        id=str(p.id),
        persona=p.persona,
        user_id=_iso_user(p.user_id),
        invitation_id=p.invitation_id,
        name=person.name,
        membership=person.membership.value,
        assignments=[s.RouteSlotRef(doc_id=pair.doc_id, slot_id=pair.slot_id) for pair in p.assignments],
        method=person.method.value if person.method is not None else None,
        state=person.view.state.value,
        next_action=person.view.next_action.value,
        approved_at=approval.at if approval is not None else None,
        notified_at=p.notified.at if p.notified is not None else None,
        reminded_at=p.reminded_at,
        reminders=p.reminders,
    )


def _summary(item: RouteSummary) -> s.SigningRouteSummary:
    route = item.route
    return s.SigningRouteSummary(
        id=str(route.id),
        profile=s.SigningProfileRef(id=route.profile_id, name=item.profile_name),
        status=item.status.value,
        phase=item.phase.value if item.phase is not None else None,
        round=route.round,
        current_step=item.current_step,
        steps_total=item.steps_total,
        deadline=route.deadline,
        stop_reason=item.stop_reason.value if item.stop_reason is not None else None,
        sent_at=route.sent_at,
        completed_at=route.completed_at,
        updated_at=_written(route.created_at, route.updated_at)[1],
        waiting_for=[s.SigningWaitingFor(name=name, persona=persona) for name, persona in item.waiting_for],
    )


def key_info(info: KeyInfo | None) -> s.SigningKeyInfo | None:
    if info is None:
        return None
    return s.SigningKeyInfo(
        id=str(info.id), label=info.label, kind=info.kind, protected=info.protected, signer=info.signer
    )


def _preview(preview: RoutePreview) -> s.SigningRoutePreview:
    return s.SigningRoutePreview(
        route_id=str(preview.route.id),
        can_send=preview.can_send,
        can_send_and_sign=preview.can_send_and_sign,
        visual_step=preview.visual_step,
        docs=[
            s.SigningRoutePreviewDoc(doc_id=doc_id, name=name, built=built, token=token)
            for doc_id, name, built, token in preview.docs
        ],
        participants=[
            s.SigningRoutePreviewParticipant(
                participant_id=str(person.participant.id),
                step=person.step,
                persona=person.participant.persona,
                name=person.name,
                membership=person.membership.value,
                method=person.method.value if person.method is not None else None,
                methods=[cast(s.RouteSignMethodName, m) for m in person.methods],
                chooses_method=person.chooses_method,
                image_ready=person.image_ready,
                plate_ready=person.plate_ready,
                actions=min(person.actions, 2),
            )
            for person in preview.participants
        ],
        blockers=[s.SigningRouteBlocker(**blocker_body(b)) for b in preview.blockers],
        sender_key=key_info(preview.sender_key),
    )


# --- запросы ---------------------------------------------------------------------------------------------------------


def _update(body: s.UpdateSigningRouteRequest) -> RouteUpdate:
    return RouteUpdate(
        steps=tuple(
            tuple(
                PersonDraft(
                    persona=d.persona,
                    id=_uuid(d.id),
                    user_id=_uuid(d.user_id),
                    invitation_id=d.invitation_id,
                )
                for d in step
            )
            for step in body.steps
        ),
        extra_slots=tuple(DocSlot(pair.doc_id, pair.slot_id) for pair in body.extra_slots),
        deadline=body.deadline,
        message=body.message,
    )


def _send(body: s.SendSigningRouteRequest) -> SendRequest:
    sign = None
    if body.sign is not None:
        sign = KeyRequest(identity_id=key_id(body.sign.identity_id), passphrase=body.sign.passphrase or "")
    return SendRequest(expected=dict(body.expected), sign=sign)


def key_id(value: str | None) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError:
        raise SigningKeyError(
            409, "key_not_found", localized_error(f"Ключ подписи {value} не найден", f"Signing key {value} not found")
        ) from None


def key_failure(exc: Exception) -> NoReturn:
    """Отказ подписи ключом Студии в ответе (раздел 8.1): пароль, ключ, политика, чужой слот или ошибка подписи."""
    if isinstance(exc, KeyPassphraseRequiredError):
        raise SigningKeyError(400, "passphrase_required", str(exc)) from exc
    if isinstance(exc, KeyPassphraseInvalidError):
        raise SigningKeyError(400, "passphrase_invalid", str(exc)) from exc
    if isinstance(exc, KeyNotFoundError):
        raise SigningKeyError(409, "key_not_found", str(exc)) from exc
    if isinstance(exc, SigningKeyStorageDeniedError):
        raise SigningKeyError(403, "server_keys_forbidden", str(exc)) from exc
    if isinstance(exc, PermissionError | ProjectForbiddenError):
        raise SigningKeyError(403, "forbidden", str(exc)) from exc
    raise SigningKeyError(400, "sign_failed", str(exc)) from exc


# --- маршруты -------------------------------------------------------------------------------------------------------


@router.get(_BASE, response_model=s.SigningRouteList)
async def list_signing_routes(
    project_id: UUID,
    response: Response,
    uc: FromDishka[SigningRouteDrafts],
    profile_id: str | None = Query(default=None, max_length=128),
) -> s.SigningRouteList:
    reader()
    response.headers["Cache-Control"] = "no-store"
    return s.SigningRouteList(items=[_summary(item) for item in await uc.list_routes(project_id, profile_id)])


@router.post(_BASE, response_model=s.SigningRouteResponse, status_code=status.HTTP_201_CREATED)
async def create_signing_route(
    project_id: UUID, body: s.CreateSigningRouteRequest, response: Response, uc: FromDishka[SigningRouteDrafts]
) -> s.SigningRouteResponse:
    """Черновик точки: незавершённый маршрут (200) или новый из пака (201)."""
    details, created = await uc.create(people_views.require_user(), project_id, body.profile_id)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return route_response(details)


@router.get(_BASE + "/{route_id}", response_model=s.SigningRouteResponse)
async def get_signing_route(
    project_id: UUID, route_id: UUID, response: Response, uc: FromDishka[SigningRouteDrafts]
) -> s.SigningRouteResponse:
    actor = reader()
    response.headers["Cache-Control"] = "no-store"
    return route_response(await uc.get(actor, project_id, route_id))


@router.put(_BASE + "/{route_id}", response_model=s.SigningRouteResponse)
async def update_signing_route(
    project_id: UUID, route_id: UUID, body: s.UpdateSigningRouteRequest, uc: FromDishka[SigningRouteDrafts]
) -> s.SigningRouteResponse:
    return route_response(await uc.update(people_views.require_user(), project_id, route_id, _update(body)))


@router.post(_BASE + "/{route_id}/preview", response_model=s.SigningRoutePreview)
async def preview_signing_route(
    project_id: UUID,
    route_id: UUID,
    response: Response,
    uc: FromDishka[SigningRouteSending],
    body: s.EmptyRequest | None = None,
) -> s.SigningRoutePreview:
    """Что будет при отправке сохранённого маршрута; ничего не меняет."""
    response.headers["Cache-Control"] = "no-store"
    return _preview(await uc.preview(people_views.require_user(), project_id, route_id))


@router.post(_BASE + "/{route_id}/send", response_model=s.SigningRouteResponse)
async def send_signing_route(
    project_id: UUID, route_id: UUID, body: s.SendSigningRouteRequest, uc: FromDishka[SigningRouteSending]
) -> s.SigningRouteResponse:
    """Отправить или отправить заново; `sign` для «Отправить и подписать»."""
    try:
        details = await uc.send(people_views.require_user(), project_id, route_id, _send(body))
    except (RouteInputError, RouteConflictError, NotFoundError):
        raise
    except (ValueError, PermissionError, ProjectForbiddenError) as exc:
        key_failure(exc)
    return route_response(details)


@router.post(_BASE + "/{route_id}/cancel", response_model=s.SigningRouteResponse)
async def cancel_signing_route(
    project_id: UUID, route_id: UUID, uc: FromDishka[SigningRouteControl], body: s.EmptyRequest | None = None
) -> s.SigningRouteResponse:
    return route_response(await uc.cancel(people_views.require_user(), project_id, route_id))


@router.post(_BASE + "/{route_id}/archive", response_model=s.SigningRouteResponse)
async def archive_signing_route(
    project_id: UUID, route_id: UUID, uc: FromDishka[SigningRouteControl], body: s.EmptyRequest | None = None
) -> s.SigningRouteResponse:
    return route_response(await uc.archive(people_views.require_user(), project_id, route_id))


@router.post(_BASE + "/{route_id}/participants/{participant_id}/remind", response_model=s.SigningReminder)
async def remind_signing_participant(
    project_id: UUID,
    route_id: UUID,
    participant_id: str,
    uc: FromDishka[SigningRouteReminding],
    body: s.EmptyRequest | None = None,
) -> s.SigningReminder:
    """Напомнить тому, чья очередь (не чаще раза в 12 часов); приглашённому повторить приглашение."""
    try:
        participant = UUID(participant_id)
    except ValueError:
        raise _not_found() from None
    reminder = await uc.remind(people_views.require_user(), project_id, route_id, participant)
    return s.SigningReminder(
        participant_id=str(reminder.participant_id), delivery=reminder.delivery, link=reminder.link
    )
