"""Приглашения в проект и запросы доступа глазами проекта (ACCESS_MANAGE), передача владения (PROJECT_TRANSFER)."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from hse_doc_studio.api import invitation_views as views
from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.rate_limit import enforce
from hse_doc_studio.api.schemas import invitations as s
from hse_doc_studio.api.schemas.admin import PageParams, page_params
from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.policy import can
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.invitations.entities import MemberTerms
from hse_doc_studio.core.rate_limit import INVITE
from hse_doc_studio.use_cases.projects.access_requests import (
    ApproveAccessRequestUC,
    DenyAccessRequestUC,
    ListAccessRequestsUC,
)
from hse_doc_studio.use_cases.projects.invitations import (
    CreateInvitationUC,
    InvitationCreated,
    ListProjectInvitationsUC,
    NewInvitation,
    ResendInvitationUC,
    RevokeInvitationUC,
)
from hse_doc_studio.use_cases.projects.transfer import (
    CancelTransferUC,
    GetTransferStateUC,
    StartTransferUC,
    TransferState,
)

router = APIRouter(dependencies=[Depends(require_server_mode)])

StatusFilter = Literal["pending", "all"]


async def _get[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _created(result: InvitationCreated) -> s.ProjectInvitationCreated:
    return s.ProjectInvitationCreated(
        invitation=views.invitation(result.view, utc_now()), delivery=result.delivery, link=result.link
    )


def _terms(body: s.ApproveAccessRequest | s.CreateProjectInvitationRequest) -> MemberTerms:
    return MemberTerms(
        role=Role(body.role),
        persona=body.persona,
        can_share=body.can_share,
        show_sources=body.show_sources,
        can_edit_all=body.can_edit_all,
    )


@router.get("/projects/{project_id}/invitations", response_model=s.ProjectInvitationPage)
async def list_invitations(
    project_id: UUID,
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    status_filter: Annotated[StatusFilter, Query(alias="status")] = "pending",
) -> s.ProjectInvitationPage:
    response.headers["Cache-Control"] = "no-store"
    uc = await _get(request, ListProjectInvitationsUC)
    found = await uc.execute(project_id, pending_only=status_filter == "pending", window=params.window)
    now = utc_now()
    return s.ProjectInvitationPage(
        items=[views.invitation(v, now) for v in found.items],
        total=found.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post(
    "/projects/{project_id}/invitations",
    response_model=s.ProjectInvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    project_id: UUID, body: s.CreateProjectInvitationRequest, request: Request
) -> s.ProjectInvitationCreated:
    actor = views.require_user()
    await enforce(request, INVITE, f"user:{actor.id}")
    uc = await _get(request, CreateInvitationUC)
    result = await uc.execute(
        actor,
        project_id,
        NewInvitation(
            terms=_terms(body),
            user_id=body.user_id,
            email=body.email,
            message=body.message,
            expires_in_days=body.expires_in_days,
        ),
    )
    return _created(result)


@router.post("/projects/{project_id}/invitations/{invitation_id}/resend", response_model=s.ProjectInvitationCreated)
async def resend_invitation(project_id: UUID, invitation_id: str, request: Request) -> s.ProjectInvitationCreated:
    actor = views.require_user()
    await enforce(request, INVITE, f"user:{actor.id}")
    uc = await _get(request, ResendInvitationUC)
    return _created(await uc.execute(actor, project_id, invitation_id))


@router.delete("/projects/{project_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(project_id: UUID, invitation_id: str, request: Request) -> Response:
    uc = await _get(request, RevokeInvitationUC)
    await uc.execute(views.require_user(), project_id, invitation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/access-requests", response_model=s.AccessRequestPage)
async def list_access_requests(
    project_id: UUID,
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    status_filter: Annotated[StatusFilter, Query(alias="status")] = "pending",
) -> s.AccessRequestPage:
    response.headers["Cache-Control"] = "no-store"
    uc = await _get(request, ListAccessRequestsUC)
    found = await uc.execute(project_id, pending_only=status_filter == "pending", window=params.window)
    return s.AccessRequestPage(
        items=[views.access_request(v) for v in found.items],
        total=found.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.post("/projects/{project_id}/access-requests/{request_id}/approve", response_model=s.AccessRequestView)
async def approve_access_request(
    project_id: UUID, request_id: str, body: s.ApproveAccessRequest, request: Request
) -> s.AccessRequestView:
    uc = await _get(request, ApproveAccessRequestUC)
    return views.access_request(await uc.execute(views.require_user(), project_id, request_id, _terms(body)))


@router.post("/projects/{project_id}/access-requests/{request_id}/deny", response_model=s.AccessRequestView)
async def deny_access_request(
    project_id: UUID, request_id: str, body: s.DenyAccessRequest, request: Request
) -> s.AccessRequestView:
    uc = await _get(request, DenyAccessRequestUC)
    return views.access_request(await uc.execute(views.require_user(), project_id, request_id))


def _state(state: TransferState) -> s.ProjectTransferState:
    return s.ProjectTransferState(
        pending=state.pending, transfer=views.transfer_info(state.view) if state.view is not None else None
    )


@router.get("/projects/{project_id}/transfer", response_model=s.ProjectTransferState)
async def get_transfer(project_id: UUID, request: Request, response: Response) -> s.ProjectTransferState:
    response.headers["Cache-Control"] = "no-store"
    actor = views.require_user()
    acl = await (await _get(request, IProjectAclRepository)).load_for(actor, project_id)  # type: ignore[type-abstract]
    uc = await _get(request, GetTransferStateUC)
    return _state(await uc.execute(project_id, can_transfer=can(actor, Action.PROJECT_TRANSFER, acl)))


@router.post(
    "/projects/{project_id}/transfer", response_model=s.ProjectTransferState, status_code=status.HTTP_201_CREATED
)
async def start_transfer(
    project_id: UUID, body: s.StartProjectTransferRequest, request: Request
) -> s.ProjectTransferState:
    uc = await _get(request, StartTransferUC)
    state = await uc.execute(
        views.require_user(),
        project_id,
        body.to_kind,
        body.to_id,
        message=body.message,
        confirm_name=body.confirm_name,
    )
    return _state(state)


@router.delete("/projects/{project_id}/transfer", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_transfer(project_id: UUID, request: Request) -> Response:
    uc = await _get(request, CancelTransferUC)
    await uc.execute(views.require_user(), project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
