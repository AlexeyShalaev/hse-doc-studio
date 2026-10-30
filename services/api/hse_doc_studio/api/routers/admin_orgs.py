"""`/api/admin/orgs*`: организации, участники и группы глазами админа установки.

Админ распоряжается всеми организациями без членства; не найденная организация отвечает 404.
Формы ответов совпадают с `contracts/server/fixtures` (AdminOrg, AdminOrgMember, AdminGroup). Списки
листаются, ищут и сортируются на сервере; состав группы меняется точечно.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from hse_doc_studio.api.schemas.admin import PageParams, page_params, search_param, sort_param
from hse_doc_studio.api.schemas.session import (
    AddAdminOrgMemberRequest,
    AdminGroup,
    AdminGroupMember,
    AdminGroupMemberPage,
    AdminGroupMemberRef,
    AdminGroupPage,
    AdminOrg,
    AdminOrgMember,
    AdminOrgMemberFacets,
    AdminOrgMemberPage,
    AdminOrgPage,
    CreateAdminGroupRequest,
    CreateAdminOrgRequest,
    OrgRoleName,
    UpdateAdminGroupRequest,
    UpdateAdminOrgMemberRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.listing import SortKey
from hse_doc_studio.core.orgs.entities import (
    GROUP_MEMBER_SORTS,
    GROUP_SORTS,
    MEMBER_SORTS,
    ORG_SORTS,
    AdminOrgSummary,
    GroupMemberQuery,
    GroupMemberView,
    GroupPreview,
    GroupQuery,
    MemberQuery,
    OrgMemberView,
    OrgQuery,
    OrgRole,
)
from hse_doc_studio.use_cases.admin.orgs import (
    AddAdminGroupMemberUC,
    AddAdminMemberUC,
    AdminMemberFacetsUC,
    CreateAdminGroupUC,
    CreateAdminOrgUC,
    DeleteAdminGroupUC,
    DeleteAdminOrgUC,
    GetAdminOrgUC,
    ListAdminGroupMembersUC,
    ListAdminGroupsUC,
    ListAdminMembersUC,
    ListAdminOrgsUC,
    RemoveAdminGroupMemberUC,
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
        owner_count=found.owner_count,
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


def _group(view: GroupPreview) -> AdminGroup:
    return AdminGroup(
        id=view.group.id,
        name=view.group.name,
        member_count=view.member_count,
        preview=[AdminGroupMemberRef(user_id=m.user_id, name=m.name) for m in view.preview],
    )


def _group_member(view: GroupMemberView) -> AdminGroupMember:
    return AdminGroupMember(user_id=view.user_id, name=view.name, email=view.email, added_at=view.added_at)


_org_sort = sort_param(allowed=ORG_SORTS, default="name")
_member_sort = sort_param(allowed=MEMBER_SORTS, default="joined_at")
_group_sort = sort_param(allowed=GROUP_SORTS, default="name")
_group_member_sort = sort_param(allowed=GROUP_MEMBER_SORTS, default="name")


@router.get("/orgs", response_model=AdminOrgPage)
async def list_orgs(
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_org_sort)],
    mine: Annotated[bool | None, Query(description="Только организации, где админ сам участник")] = None,
) -> AdminOrgPage:
    response.headers.update(_NO_STORE)
    query = OrgQuery(q=q, mine=mine, sort=sort, window=params.window)
    found = await (await _uc(request, ListAdminOrgsUC)).execute(_actor(), query)
    return AdminOrgPage(
        items=[_org(x) for x in found.items], total=found.total, limit=params.limit, offset=params.offset
    )


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


@router.get("/orgs/{slug}/members", response_model=AdminOrgMemberPage)
async def list_members(
    slug: str,
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_member_sort)],
    role: Annotated[list[OrgRoleName] | None, Query()] = None,
) -> AdminOrgMemberPage:
    """Тот же список служит пикером участников группы: `?q=&limit=20`."""
    response.headers.update(_NO_STORE)
    query = MemberQuery(q=q, roles=tuple(OrgRole(r) for r in role or ()), sort=sort, window=params.window)
    found = await (await _uc(request, ListAdminMembersUC)).execute(_actor(), slug, query)
    return AdminOrgMemberPage(
        items=[_member(x) for x in found.items], total=found.total, limit=params.limit, offset=params.offset
    )


@router.get("/orgs/{slug}/members/facets", response_model=AdminOrgMemberFacets)
async def member_facets(
    slug: str, request: Request, response: Response, q: Annotated[str | None, Depends(search_param)]
) -> AdminOrgMemberFacets:
    response.headers.update(_NO_STORE)
    counts = await (await _uc(request, AdminMemberFacetsUC)).execute(_actor(), slug, q)
    return AdminOrgMemberFacets(role={r.value: n for r, n in counts.items()})


@router.post("/orgs/{slug}/members", response_model=AdminOrgMember, status_code=status.HTTP_201_CREATED)
async def add_member(slug: str, body: AddAdminOrgMemberRequest, request: Request, response: Response) -> AdminOrgMember:
    response.headers.update(_NO_STORE)
    uc = await _uc(request, AddAdminMemberUC)
    return _member(await uc.execute(_actor(), slug, role=OrgRole(body.role), user_id=body.user_id, email=body.email))


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


@router.get("/orgs/{slug}/groups", response_model=AdminGroupPage)
async def list_groups(
    slug: str,
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_group_sort)],
) -> AdminGroupPage:
    response.headers.update(_NO_STORE)
    query = GroupQuery(q=q, sort=sort, window=params.window)
    found = await (await _uc(request, ListAdminGroupsUC)).execute(_actor(), slug, query)
    return AdminGroupPage(
        items=[_group(x) for x in found.items], total=found.total, limit=params.limit, offset=params.offset
    )


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


@router.get("/orgs/{slug}/groups/{group_id}/members", response_model=AdminGroupMemberPage)
async def list_group_members(
    slug: str,
    group_id: str,
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_group_member_sort)],
) -> AdminGroupMemberPage:
    response.headers.update(_NO_STORE)
    query = GroupMemberQuery(q=q, sort=sort, window=params.window)
    found = await (await _uc(request, ListAdminGroupMembersUC)).execute(_actor(), slug, group_id, query)
    return AdminGroupMemberPage(
        items=[_group_member(x) for x in found.items], total=found.total, limit=params.limit, offset=params.offset
    )


@router.post(
    "/orgs/{slug}/groups/{group_id}/members/{user_id}",
    response_model=AdminGroupMember,
    status_code=status.HTTP_201_CREATED,
)
async def add_group_member(
    slug: str, group_id: str, user_id: str, request: Request, response: Response
) -> AdminGroupMember:
    """Точечное добавление: в группу входят только участники организации (иначе 422), повтор даёт 409."""
    response.headers.update(_NO_STORE)
    uc = await _uc(request, AddAdminGroupMemberUC)
    return _group_member(await uc.execute(_actor(), slug, group_id, user_id))


@router.delete("/orgs/{slug}/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(slug: str, group_id: str, user_id: str, request: Request) -> Response:
    await (await _uc(request, RemoveAdminGroupMemberUC)).execute(_actor(), slug, group_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
