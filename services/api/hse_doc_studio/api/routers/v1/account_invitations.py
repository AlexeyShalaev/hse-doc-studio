"""Адресат приглашений и передач, запросы доступа просящего, ссылка из письма и «Входящие»."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from hse_doc_studio.api import invitation_views as views
from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.rate_limit import enforce, enforce_ip
from hse_doc_studio.api.schemas import invitations as s
from hse_doc_studio.api.schemas.admin import PageParams, page_params
from hse_doc_studio.core.access.entities import ActorSource
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.rate_limit import ACCESS_REQUEST, AUTH_IP
from hse_doc_studio.use_cases.notifications.inbox import (
    InboxSummaryUC,
    ListNotificationsUC,
    MarkNotificationsReadUC,
)
from hse_doc_studio.use_cases.projects.access_requests import (
    CancelAccessRequestUC,
    CreateAccessRequestUC,
    ListMyAccessRequestsUC,
)
from hse_doc_studio.use_cases.projects.invitations import (
    AcceptInvitationTokenUC,
    AcceptInvitationUC,
    DeclineInvitationUC,
    ListMyInvitationsUC,
    PreviewInvitationTokenUC,
)
from hse_doc_studio.use_cases.projects.transfer import AcceptTransferUC, DeclineTransferUC, ListMyTransfersUC

router = APIRouter(dependencies=[Depends(require_server_mode)])


async def _get[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


# Приглашения адресата


@router.get("/account/invitations", response_model=s.MyInvitationList)
async def my_invitations(request: Request, response: Response) -> s.MyInvitationList:
    _no_store(response)
    items = await (await _get(request, ListMyInvitationsUC)).execute(views.require_user())
    now = utc_now()
    return s.MyInvitationList(items=[views.my_invitation(v, now) for v in items])


@router.post("/account/invitations/{invitation_id}/accept", response_model=s.MyInvitation)
async def accept_invitation(invitation_id: str, request: Request) -> s.MyInvitation:
    view = await (await _get(request, AcceptInvitationUC)).execute(views.require_user(), invitation_id)
    return views.my_invitation(view, utc_now())


@router.post("/account/invitations/{invitation_id}/decline", response_model=s.MyInvitation)
async def decline_invitation(invitation_id: str, request: Request) -> s.MyInvitation:
    view = await (await _get(request, DeclineInvitationUC)).execute(views.require_user(), invitation_id)
    return views.my_invitation(view, utc_now())


@router.get("/project-invitations/{token}", response_model=s.ProjectInvitationPreview)
async def preview_invitation(token: str, request: Request, response: Response) -> s.ProjectInvitationPreview:
    """Публичная карточка приглашения по ссылке из письма; имя проекта только у действующего."""
    _no_store(response)
    response.headers["Referrer-Policy"] = "no-referrer"
    await enforce_ip(request, AUTH_IP)
    preview = await (await _get(request, PreviewInvitationTokenUC)).execute(token[:512])
    return s.ProjectInvitationPreview(
        state=preview.state,
        project_name=preview.project_name,
        inviter_name=preview.inviter_name,
        role=views.grant_role(preview.role) if preview.role else None,
        email_hint=preview.email_hint,
        registration_token=preview.registration_token,
    )


@router.post("/project-invitations/{token}/accept", response_model=s.MyInvitation)
async def accept_invitation_by_token(token: str, request: Request) -> s.MyInvitation:
    view = await (await _get(request, AcceptInvitationTokenUC)).execute(views.require_user(), token[:512])
    return views.my_invitation(view, utc_now())


# Запросы доступа просящего


@router.post("/access-requests", response_model=s.AccessRequestAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_access_request(body: s.CreateAccessRequest, request: Request) -> s.AccessRequestAccepted:
    """Ответ одинаков для существующего и несуществующего проекта (S13)."""
    actor = views.require_user()
    # Только сессия: утёкший токен не должен рассылать запросы от имени человека.
    if actor.source is ActorSource.pat:
        raise IdentityError(IdentityErrorCode.forbidden)
    await enforce(request, ACCESS_REQUEST, f"user:{actor.id}")
    await (await _get(request, CreateAccessRequestUC)).execute(actor, body.project, body.message)
    return s.AccessRequestAccepted()


@router.get("/account/access-requests", response_model=s.MyAccessRequestList)
async def my_access_requests(request: Request, response: Response) -> s.MyAccessRequestList:
    _no_store(response)
    items = await (await _get(request, ListMyAccessRequestsUC)).execute(views.require_user())
    return s.MyAccessRequestList(items=[views.my_access_request(v) for v in items])


@router.delete("/account/access-requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_access_request(request_id: str, request: Request) -> Response:
    await (await _get(request, CancelAccessRequestUC)).execute(views.require_user(), request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Передачи получателю


@router.get("/account/transfers", response_model=s.MyTransferList)
async def my_transfers(request: Request, response: Response) -> s.MyTransferList:
    _no_store(response)
    items = await (await _get(request, ListMyTransfersUC)).execute(views.require_user())
    now = utc_now()
    return s.MyTransferList(items=[views.my_transfer(v, now) for v in items])


@router.post("/account/transfers/{transfer_id}/accept", response_model=s.MyTransfer)
async def accept_transfer(transfer_id: str, request: Request) -> s.MyTransfer:
    view = await (await _get(request, AcceptTransferUC)).execute(views.require_user(), transfer_id)
    return views.my_transfer(view, utc_now())


@router.post("/account/transfers/{transfer_id}/decline", response_model=s.MyTransfer)
async def decline_transfer(transfer_id: str, request: Request) -> s.MyTransfer:
    view = await (await _get(request, DeclineTransferUC)).execute(views.require_user(), transfer_id)
    return views.my_transfer(view, utc_now())


# «Входящие»


@router.get("/account/notifications", response_model=s.NotificationPage)
async def notifications(
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    unread: Annotated[bool, Query()] = False,
) -> s.NotificationPage:
    _no_store(response)
    found = await (await _get(request, ListNotificationsUC)).execute(
        views.require_user(), unread_only=unread, window=params.window
    )
    return s.NotificationPage(
        items=[views.notification(n) for n in found.items],
        total=found.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post("/account/notifications/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notifications_read(body: s.MarkNotificationsReadRequest, request: Request) -> Response:
    await (await _get(request, MarkNotificationsReadUC)).execute(views.require_user(), body.ids)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/account/inbox/summary", response_model=s.InboxSummary)
async def inbox_summary(request: Request, response: Response) -> s.InboxSummary:
    _no_store(response)
    summary = await (await _get(request, InboxSummaryUC)).execute(views.require_user())
    return s.InboxSummary(
        unread=summary.unread,
        invitations=summary.invitations,
        transfers=summary.transfers,
        access_requests=summary.access_requests,
    )
