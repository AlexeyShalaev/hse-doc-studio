"""`/api/admin`: люди установки (пользователи, одобрения, приглашения). Содержимого проектов эти ручки не отдают."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from hse_doc_studio.api.schemas.admin import PageParams, page_params
from hse_doc_studio.api.schemas.session import (
    AccountStatus,
    AdminInvitation,
    AdminInvitationCreated,
    AdminInvitationPage,
    AdminResetLink,
    AdminResetLinkRequest,
    AdminSessionsRevoked,
    AdminUser,
    AdminUserPage,
    CreateAdminInvitationRequest,
    UpdateAdminUserRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import RegistrationInvite, UserListing, UserStatus
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import is_valid_email
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.use_cases.admin.invitations import ResendInviteUC
from hse_doc_studio.use_cases.admin.lifecycle import DeleteUserUC
from hse_doc_studio.use_cases.admin.users import (
    ApproveUserUC,
    DisableUserUC,
    EnableUserUC,
    GetUserUC,
    ListApprovalsUC,
    ListUsersUC,
    RejectUserUC,
    RevokeUserSessionsUC,
    SetUserAdminUC,
)
from hse_doc_studio.use_cases.identity.invites import (
    DEFAULT_INVITE_TTL,
    CreatedInvite,
    CreateInviteUC,
    ListInvitesUC,
    RevokeInviteUC,
)
from hse_doc_studio.use_cases.identity.recovery import IssueResetLinkUC

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}
_MAX_TTL_DAYS = 30


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


def _user(listing: UserListing) -> AdminUser:
    user = listing.user
    return AdminUser(
        id=user.id,
        name=user.name,
        email=user.email,
        status=user.status.value,
        is_instance_admin=user.is_instance_admin,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
        project_count=listing.project_count,
    )


def _invitation(invite: RegistrationInvite) -> AdminInvitation:
    if invite.used_at is not None:
        state = "used"
    elif invite.expires_at <= utc_now():
        state = "expired"
    else:
        state = "pending"
    return AdminInvitation(
        id=invite.id, email=invite.email, status=state, expires_at=invite.expires_at, used_at=invite.used_at
    )


def _created(created: CreatedInvite) -> AdminInvitationCreated:
    return AdminInvitationCreated(invitation=_invitation(created.invite), link=created.link)


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    request: Request,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    account_status: Annotated[AccountStatus | None, Query(alias="status")] = None,
) -> AdminUserPage:
    page = await (await _uc(request, ListUsersUC)).execute(
        _actor(),
        q=q,
        status=UserStatus(account_status) if account_status else None,
        limit=params.limit,
        offset=params.offset,
    )
    return AdminUserPage(
        items=[_user(x) for x in page.items], total=page.total, limit=params.limit, offset=params.offset
    )


@router.get("/users/{user_id}", response_model=AdminUser)
async def get_user(user_id: str, request: Request) -> AdminUser:
    return _user(await (await _uc(request, GetUserUC)).execute(_actor(), user_id))


async def _changed(request: Request, user_id: str) -> AdminUser:
    return _user(await (await _uc(request, GetUserUC)).execute(_actor(), user_id))


@router.patch("/users/{user_id}", response_model=AdminUser)
async def update_user(user_id: str, body: UpdateAdminUserRequest, request: Request) -> AdminUser:
    await (await _uc(request, SetUserAdminUC)).execute(_actor(), user_id, is_admin=body.is_instance_admin)
    return await _changed(request, user_id)


@router.post("/users/{user_id}/disable", response_model=AdminUser)
async def disable_user(user_id: str, request: Request) -> AdminUser:
    await (await _uc(request, DisableUserUC)).execute(_actor(), user_id)
    return await _changed(request, user_id)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, request: Request) -> Response:
    """Окончательное удаление отключённой учётной записи: личные данные стираются, журнал обезличивается."""
    await (await _uc(request, DeleteUserUC)).execute(_actor(), user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/users/{user_id}/enable", response_model=AdminUser)
async def enable_user(user_id: str, request: Request) -> AdminUser:
    await (await _uc(request, EnableUserUC)).execute(_actor(), user_id)
    return await _changed(request, user_id)


@router.post("/users/{user_id}/reset-link", response_model=AdminResetLink)
async def issue_reset_link(
    user_id: str, body: AdminResetLinkRequest, request: Request, response: Response
) -> AdminResetLink:
    """Break-glass: ссылка сброса пароля выдаётся с подтверждением, событием аудита и письмом-уведомлением."""
    if not body.confirm:
        raise IdentityError(IdentityErrorCode.forbidden)
    await (await _uc(request, GetUserUC)).execute(_actor(), user_id)
    issued = await (await _uc(request, IssueResetLinkUC)).execute(_actor(), user_id, confirmed=True)
    response.headers.update(_NO_STORE)
    return AdminResetLink(link=issued.link, expires_at=issued.expires_at, user_notified=issued.user_notified)


@router.post("/users/{user_id}/sessions/revoke", response_model=AdminSessionsRevoked)
async def revoke_sessions(user_id: str, request: Request) -> AdminSessionsRevoked:
    revoked = await (await _uc(request, RevokeUserSessionsUC)).execute(_actor(), user_id)
    return AdminSessionsRevoked(revoked=revoked)


@router.get("/approvals", response_model=AdminUserPage)
async def list_approvals(request: Request, params: Annotated[PageParams, Depends(page_params)]) -> AdminUserPage:
    page = await (await _uc(request, ListApprovalsUC)).execute(_actor(), limit=params.limit, offset=params.offset)
    return AdminUserPage(
        items=[_user(x) for x in page.items], total=page.total, limit=params.limit, offset=params.offset
    )


@router.post("/approvals/{user_id}/approve", response_model=AdminUser)
async def approve(user_id: str, request: Request) -> AdminUser:
    await (await _uc(request, ApproveUserUC)).execute(_actor(), user_id)
    return await _changed(request, user_id)


@router.post("/approvals/{user_id}/reject", response_model=AdminUser)
async def reject(user_id: str, request: Request) -> AdminUser:
    await (await _uc(request, RejectUserUC)).execute(_actor(), user_id)
    return await _changed(request, user_id)


@router.get("/invitations", response_model=AdminInvitationPage)
async def list_invitations(
    request: Request, params: Annotated[PageParams, Depends(page_params)]
) -> AdminInvitationPage:
    invites = await (await _uc(request, ListInvitesUC)).execute(_actor())
    window = invites[params.offset : params.offset + params.limit]
    return AdminInvitationPage(
        items=[_invitation(i) for i in window], total=len(invites), limit=params.limit, offset=params.offset
    )


@router.post("/invitations", response_model=AdminInvitationCreated, status_code=status.HTTP_201_CREATED)
async def create_invitation(
    body: CreateAdminInvitationRequest, request: Request, response: Response
) -> AdminInvitationCreated:
    if body.email is not None and not is_valid_email(body.email):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid email")
    if body.ttl_days is not None and not 1 <= body.ttl_days <= _MAX_TTL_DAYS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid ttl_days")
    ttl = timedelta(days=body.ttl_days) if body.ttl_days else DEFAULT_INVITE_TTL
    created = await (await _uc(request, CreateInviteUC)).execute(_actor(), email=body.email, ttl=ttl)
    response.headers.update(_NO_STORE)
    return _created(created)


@router.post("/invitations/{invite_id}/resend", response_model=AdminInvitationCreated)
async def resend_invitation(invite_id: str, request: Request, response: Response) -> AdminInvitationCreated:
    created = await (await _uc(request, ResendInviteUC)).execute(_actor(), invite_id)
    response.headers.update(_NO_STORE)
    return _created(created)


@router.delete("/invitations/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_invitation(invite_id: str, request: Request) -> Response:
    try:
        await (await _uc(request, RevokeInviteUC)).execute(_actor(), invite_id)
    except IdentityError as exc:
        if exc.code is IdentityErrorCode.invitation_invalid:
            raise IdentityError(IdentityErrorCode.not_found) from exc
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
