"""`/api/admin/orgs*`: организации, участники и группы глазами админа установки.

Админ распоряжается всеми организациями без членства; не найденная организация отвечает 404.
Формы ответов совпадают с `contracts/server/fixtures` (AdminOrg, AdminOrgMember, AdminGroup).
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response, status

from hse_doc_studio.api.schemas.session import (
    AddAdminOrgMemberRequest,
    AdminGroup,
    AdminOrg,
    AdminOrgMember,
    CreateAdminGroupRequest,
    CreateAdminOrgRequest,
    UpdateAdminGroupRequest,
    UpdateAdminOrgMemberRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import AdminOrgSummary, OrgMemberView, OrgRole
from hse_doc_studio.use_cases.admin.orgs import (
    AddAdminMemberUC,
    AdminGroupView,
    CreateAdminGroupUC,
    CreateAdminOrgUC,
    DeleteAdminGroupUC,
    DeleteAdminOrgUC,
    GetAdminOrgUC,
    ListAdminGroupsUC,
    ListAdminMembersUC,
    ListAdminOrgsUC,
    RemoveAdminMemberUC,
    SetAdminMemberRoleUC,
    UpdateAdminGroupUC,
)

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _org(found: AdminOrgSummary) -> AdminOrg:
    return AdminOrg(
        slug=found.org.slug,
        name=found.org.name,
        member_count=found.member_count,
        project_count=found.project_count,
        my_role=found.my_role.value if found.my_role else None,
    )


def _member(view: OrgMemberView) -> AdminOrgMember:
    return AdminOrgMember(
        user_id=view.member.user_id,
        name=view.name,
        email=view.email,
        role=view.member.role.value,
        joined_at=view.member.created_at,
    )


def _group(view: AdminGroupView) -> AdminGroup:
    return AdminGroup(id=view.group.id, name=view.group.name, member_ids=view.member_ids)


@router.get("/orgs", response_model=list[AdminOrg])
async def list_orgs(request: Request, response: Response) -> list[AdminOrg]:
    response.headers.update(_NO_STORE)
    return [_org(x) for x in await (await _uc(request, ListAdminOrgsUC)).execute(_actor())]


@router.post("/orgs", response_model=AdminOrg, status_code=status.HTTP_201_CREATED)
async def create_org(body: CreateAdminOrgRequest, request: Request, response: Response) -> AdminOrg:
    response.headers.update(_NO_STORE)
    return _org(await (await _uc(request, CreateAdminOrgUC)).execute(_actor(), slug=body.slug, name=body.name))


@router.get("/orgs/{slug}", response_model=AdminOrg)
async def get_org(slug: str, request: Request, response: Response) -> AdminOrg:
    response.headers.update(_NO_STORE)
    return _org(await (await _uc(request, GetAdminOrgUC)).execute(_actor(), slug))


@router.delete("/orgs/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(slug: str, request: Request) -> Response:
    await (await _uc(request, DeleteAdminOrgUC)).execute(_actor(), slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/orgs/{slug}/members", response_model=list[AdminOrgMember])
async def list_members(slug: str, request: Request, response: Response) -> list[AdminOrgMember]:
    response.headers.update(_NO_STORE)
    return [_member(x) for x in await (await _uc(request, ListAdminMembersUC)).execute(_actor(), slug)]


@router.post("/orgs/{slug}/members", response_model=AdminOrgMember, status_code=status.HTTP_201_CREATED)
async def add_member(slug: str, body: AddAdminOrgMemberRequest, request: Request, response: Response) -> AdminOrgMember:
    response.headers.update(_NO_STORE)
    uc = await _uc(request, AddAdminMemberUC)
    return _member(await uc.execute(_actor(), slug, email=body.email, role=OrgRole(body.role)))


@router.patch("/orgs/{slug}/members/{user_id}", response_model=AdminOrgMember)
async def set_member_role(
    slug: str, user_id: str, body: UpdateAdminOrgMemberRequest, request: Request, response: Response
) -> AdminOrgMember:
    response.headers.update(_NO_STORE)
    uc = await _uc(request, SetAdminMemberRoleUC)
    return _member(await uc.execute(_actor(), slug, user_id, role=OrgRole(body.role)))


@router.delete("/orgs/{slug}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(slug: str, user_id: str, request: Request) -> Response:
    await (await _uc(request, RemoveAdminMemberUC)).execute(_actor(), slug, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/orgs/{slug}/groups", response_model=list[AdminGroup])
async def list_groups(slug: str, request: Request, response: Response) -> list[AdminGroup]:
    response.headers.update(_NO_STORE)
    return [_group(x) for x in await (await _uc(request, ListAdminGroupsUC)).execute(_actor(), slug)]


@router.post("/orgs/{slug}/groups", response_model=AdminGroup, status_code=status.HTTP_201_CREATED)
async def create_group(slug: str, body: CreateAdminGroupRequest, request: Request, response: Response) -> AdminGroup:
    response.headers.update(_NO_STORE)
    uc = await _uc(request, CreateAdminGroupUC)
    return _group(await uc.execute(_actor(), slug, name=body.name, member_ids=body.member_ids))


@router.patch("/orgs/{slug}/groups/{group_id}", response_model=AdminGroup)
async def update_group(
    slug: str, group_id: str, body: UpdateAdminGroupRequest, request: Request, response: Response
) -> AdminGroup:
    response.headers.update(_NO_STORE)
    uc = await _uc(request, UpdateAdminGroupUC)
    return _group(await uc.execute(_actor(), slug, group_id, name=body.name, member_ids=body.member_ids))


@router.delete("/orgs/{slug}/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(slug: str, group_id: str, request: Request) -> Response:
    await (await _uc(request, DeleteAdminGroupUC)).execute(_actor(), slug, group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
