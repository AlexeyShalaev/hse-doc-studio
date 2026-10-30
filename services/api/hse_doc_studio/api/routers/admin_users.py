"""`/api/admin`: люди установки (пользователи, одобрения, приглашения). Содержимого проектов эти ручки не отдают."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from hse_doc_studio.api.schemas.admin import PageParams, page_params, search_param, sort_param
from hse_doc_studio.api.schemas.session import (
    AccountStatus,
    AdminInvitation,
    AdminInvitationCreated,
    AdminInvitationPage,
    AdminInvitationStatus,
    AdminResetLink,
    AdminResetLinkRequest,
    AdminSessionsRevoked,
    AdminUser,
    AdminUserFacets,
    AdminUserOrg,
    AdminUserOrgPage,
    AdminUserPage,
    CreateAdminInvitationRequest,
    OrgRoleName,
    UpdateAdminUserRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.entities import (
    INVITE_SORTS,
    USER_SORTS,
    InviteQuery,
    InviteState,
    RegistrationInvite,
    UserListing,
    UserQuery,
    UserStatus,
    invite_state,
)
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.normalize import is_valid_email
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.listing import Found, SortKey
from hse_doc_studio.core.orgs.entities import USER_ORG_SORTS, OrgRole, UserOrgQuery
from hse_doc_studio.use_cases.admin.invitations import ResendInviteUC
from hse_doc_studio.use_cases.admin.lifecycle import DeleteUserUC
from hse_doc_studio.use_cases.admin.users import (
    ApproveUserUC,
    DisableUserUC,
    EnableUserUC,
    GetUserUC,
    ListApprovalsUC,
    ListUserOrgsUC,
    ListUsersUC,
    RejectUserUC,
    RevokeUserSessionsUC,
    SetUserAdminUC,
    UserFacetsUC,
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
    return AdminInvitation(
        id=invite.id,
        email=invite.email,
        status=invite_state(invite, utc_now()).value,
        expires_at=invite.expires_at,
        used_at=invite.used_at,
    )


def _created(created: CreatedInvite) -> AdminInvitationCreated:
    return AdminInvitationCreated(invitation=_invitation(created.invite), link=created.link)


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _users_page(found: Found[UserListing], params: PageParams) -> AdminUserPage:
    return AdminUserPage(
        items=[_user(x) for x in found.items], total=found.total, limit=params.limit, offset=params.offset
    )


_user_sort = sort_param(allowed=USER_SORTS, default="-created_at")
_approval_sort = sort_param(allowed=("created_at", "name", "email"), default="created_at")
_invite_sort = sort_param(allowed=INVITE_SORTS, default="-expires_at")
_user_org_sort = sort_param(allowed=USER_ORG_SORTS, default="name")


@router.get("/users", response_model=AdminUserPage)
async def list_users(
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_user_sort)],
    account_status: Annotated[list[AccountStatus] | None, Query(alias="status")] = None,
    is_admin: bool | None = None,
    org: Annotated[str | None, Query(max_length=64, description="Состоит в организации (slug)")] = None,
) -> AdminUserPage:
    response.headers.update(_NO_STORE)
    query = UserQuery(
        q=q,
        statuses=tuple(UserStatus(x) for x in account_status or ()),
        is_admin=is_admin,
        org_slug=org,
        sort=sort,
        window=params.window,
    )
    return _users_page(await (await _uc(request, ListUsersUC)).execute(_actor(), query), params)


@router.get("/users/facets", response_model=AdminUserFacets)
async def user_facets(
    request: Request, response: Response, q: Annotated[str | None, Depends(search_param)]
) -> AdminUserFacets:
    """Счётчики на чипах статусов: один запрос вместо страницы на каждый статус."""
    response.headers.update(_NO_STORE)
    facets = await (await _uc(request, UserFacetsUC)).execute(_actor(), q)
    return AdminUserFacets(status={s.value: n for s, n in facets.status.items()}, admins=facets.admins)


@router.get("/users/{user_id}", response_model=AdminUser)
async def get_user(user_id: str, request: Request, response: Response) -> AdminUser:
    response.headers.update(_NO_STORE)
    return _user(await (await _uc(request, GetUserUC)).execute(_actor(), user_id))


@router.get("/users/{user_id}/orgs", response_model=AdminUserOrgPage)
async def list_user_orgs(
    user_id: str,
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_user_org_sort)],
    role: Annotated[list[OrgRoleName] | None, Query()] = None,
) -> AdminUserOrgPage:
    """Организации человека одним запросом: карточка не перебирает составы всех организаций."""
    response.headers.update(_NO_STORE)
    query = UserOrgQuery(q=q, roles=tuple(OrgRole(r) for r in role or ()), sort=sort, window=params.window)
    found = await (await _uc(request, ListUserOrgsUC)).execute(_actor(), user_id, query)
    return AdminUserOrgPage(
        items=[
            AdminUserOrg(slug=x.org.slug, name=x.org.name, role=x.role.value, joined_at=x.joined_at)
            for x in found.items
        ],
        total=found.total,
        limit=params.limit,
        offset=params.offset,
    )


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
async def list_approvals(
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_approval_sort)],
) -> AdminUserPage:
    """Очередь одобрения: по умолчанию старые заявки первыми, они ждут дольше всех."""
    response.headers.update(_NO_STORE)
    query = UserQuery(q=q, sort=sort, window=params.window)
    return _users_page(await (await _uc(request, ListApprovalsUC)).execute(_actor(), query), params)


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
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_invite_sort)],
    invite_status: Annotated[list[AdminInvitationStatus] | None, Query(alias="status")] = None,
    org: Annotated[str | None, Query(max_length=64, description="Приглашение в организацию (slug)")] = None,
) -> AdminInvitationPage:
    response.headers.update(_NO_STORE)
    query = InviteQuery(
        now=utc_now(),
        q=q,
        states=tuple(InviteState(x) for x in invite_status or ()),
        org_slug=org,
        sort=sort,
        window=params.window,
    )
    found = await (await _uc(request, ListInvitesUC)).execute(_actor(), query)
    return AdminInvitationPage(
        items=[_invitation(i) for i in found.items], total=found.total, limit=params.limit, offset=params.offset
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
