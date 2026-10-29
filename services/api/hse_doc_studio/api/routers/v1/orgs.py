"""Организации и группы: список своих, участники, роли, группы. Не участнику организации нет (404)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.schemas.session import (
    AddGroupMemberRequest,
    AddOrgMemberRequest,
    ChangeOrgMemberRoleRequest,
    CreateGroupRequest,
    CreateOrgRequest,
    Group,
    GroupMember,
    Org,
    OrgMember,
    UpdateGroupRequest,
    UpdateOrgRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.orgs.entities import GroupMemberView, GroupSummary, OrgMemberView, OrgRole, OrgSummary
from hse_doc_studio.use_cases.orgs.groups import (
    AddGroupMemberUC,
    CreateGroupUC,
    DeleteGroupUC,
    ListGroupMembersUC,
    ListGroupsUC,
    RemoveGroupMemberUC,
    UpdateGroupUC,
)
from hse_doc_studio.use_cases.orgs.members import (
    AddOrgMemberUC,
    ChangeOrgRoleUC,
    LeaveOrgUC,
    ListOrgMembersUC,
    RemoveOrgMemberUC,
)
from hse_doc_studio.use_cases.orgs.orgs import CreateOrgUC, DeleteOrgUC, GetOrgUC, ListMyOrgsUC, UpdateOrgUC

router = APIRouter(dependencies=[Depends(require_server_mode)])


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


async def _uc[T](request: Request, kind: type[T]) -> T:
    return await request.state.dishka_container.get(kind)


def _org(found: OrgSummary) -> Org:
    return Org(
        slug=found.org.slug,
        name=found.org.name,
        my_role=found.my_role.value,
        member_count=found.member_count,
        group_count=found.group_count,
        project_count=found.project_count,
        created_at=found.org.created_at,
    )


def _member(view: OrgMemberView) -> OrgMember:
    return OrgMember(
        user_id=view.member.user_id,
        name=view.name,
        email=view.email,
        role=view.member.role.value,
        joined_at=view.member.created_at,
    )


def _group(found: GroupSummary) -> Group:
    return Group(
        id=found.group.id, name=found.group.name, member_count=found.member_count, created_at=found.group.created_at
    )


def _group_member(view: GroupMemberView) -> GroupMember:
    return GroupMember(user_id=view.user_id, name=view.name, email=view.email, added_at=view.added_at)


@router.get("/orgs", response_model=list[Org])
async def list_orgs(request: Request, response: Response) -> list[Org]:
    response.headers["Cache-Control"] = "no-store"
    return [_org(x) for x in await (await _uc(request, ListMyOrgsUC)).execute(_actor())]


@router.post("/orgs", response_model=Org, status_code=status.HTTP_201_CREATED)
async def create_org(body: CreateOrgRequest, request: Request) -> Org:
    uc = await _uc(request, CreateOrgUC)
    return _org(await uc.execute(_actor(), slug=body.slug, name=body.name, owner_email=body.owner_email))


@router.get("/orgs/{slug}", response_model=Org)
async def get_org(slug: str, request: Request, response: Response) -> Org:
    response.headers["Cache-Control"] = "no-store"
    return _org(await (await _uc(request, GetOrgUC)).execute(_actor(), slug))


@router.patch("/orgs/{slug}", response_model=Org)
async def update_org(slug: str, body: UpdateOrgRequest, request: Request) -> Org:
    return _org(await (await _uc(request, UpdateOrgUC)).execute(_actor(), slug, name=body.name))


@router.delete("/orgs/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(slug: str, request: Request) -> Response:
    await (await _uc(request, DeleteOrgUC)).execute(_actor(), slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/orgs/{slug}/members", response_model=list[OrgMember])
async def list_members(slug: str, request: Request, response: Response) -> list[OrgMember]:
    response.headers["Cache-Control"] = "no-store"
    return [_member(x) for x in await (await _uc(request, ListOrgMembersUC)).execute(_actor(), slug)]


@router.post("/orgs/{slug}/members", response_model=OrgMember, status_code=status.HTTP_201_CREATED)
async def add_member(slug: str, body: AddOrgMemberRequest, request: Request) -> OrgMember:
    uc = await _uc(request, AddOrgMemberUC)
    return _member(await uc.execute(_actor(), slug, email=body.email, role=OrgRole(body.role)))


@router.patch("/orgs/{slug}/members/{user_id}", response_model=OrgMember)
async def change_member_role(slug: str, user_id: str, body: ChangeOrgMemberRoleRequest, request: Request) -> OrgMember:
    uc = await _uc(request, ChangeOrgRoleUC)
    return _member(await uc.execute(_actor(), slug, user_id, role=OrgRole(body.role)))


@router.delete("/orgs/{slug}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(slug: str, user_id: str, request: Request) -> Response:
    await (await _uc(request, RemoveOrgMemberUC)).execute(_actor(), slug, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/orgs/{slug}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_org(slug: str, request: Request) -> Response:
    await (await _uc(request, LeaveOrgUC)).execute(_actor(), slug)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/orgs/{slug}/groups", response_model=list[Group])
async def list_groups(slug: str, request: Request, response: Response) -> list[Group]:
    response.headers["Cache-Control"] = "no-store"
    return [_group(x) for x in await (await _uc(request, ListGroupsUC)).execute(_actor(), slug)]


@router.post("/orgs/{slug}/groups", response_model=Group, status_code=status.HTTP_201_CREATED)
async def create_group(slug: str, body: CreateGroupRequest, request: Request) -> Group:
    return _group(await (await _uc(request, CreateGroupUC)).execute(_actor(), slug, name=body.name))


@router.patch("/groups/{group_id}", response_model=Group)
async def update_group(group_id: str, body: UpdateGroupRequest, request: Request) -> Group:
    return _group(await (await _uc(request, UpdateGroupUC)).execute(_actor(), group_id, name=body.name))


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(group_id: str, request: Request) -> Response:
    await (await _uc(request, DeleteGroupUC)).execute(_actor(), group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/groups/{group_id}/members", response_model=list[GroupMember])
async def list_group_members(group_id: str, request: Request, response: Response) -> list[GroupMember]:
    response.headers["Cache-Control"] = "no-store"
    return [_group_member(x) for x in await (await _uc(request, ListGroupMembersUC)).execute(_actor(), group_id)]


@router.post("/groups/{group_id}/members", response_model=GroupMember, status_code=status.HTTP_201_CREATED)
async def add_group_member(group_id: str, body: AddGroupMemberRequest, request: Request) -> GroupMember:
    uc = await _uc(request, AddGroupMemberUC)
    return _group_member(await uc.execute(_actor(), group_id, user_id=body.user_id))


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_group_member(group_id: str, user_id: str, request: Request) -> Response:
    await (await _uc(request, RemoveGroupMemberUC)).execute(_actor(), group_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
