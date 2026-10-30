"""Участники проекта на сервере: роль человеку или группе и её снятие. Правит владелец проекта."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.schemas.admin import (
    PageParams,
    PickerItem,
    PickerList,
    PickerParams,
    page_params,
    picker_params,
    search_param,
    sort_param,
)
from hse_doc_studio.api.schemas.session import (
    ProjectAccessCandidate,
    ProjectAccessCandidateList,
    ProjectAccessEntry,
    ProjectAccessPage,
    ProjectMember,
    ProjectMemberKind,
    ProjectRoleName,
    SetProjectMemberRequest,
)
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import ACCESS_SORTS, AccessQuery, ProjectMemberGrant
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.listing import SortKey
from hse_doc_studio.use_cases.projects.access_panel import (
    ListAccessCandidatesUC,
    ListProjectAccessUC,
    ListTransferCandidatesUC,
)
from hse_doc_studio.use_cases.projects.members import RemoveProjectMemberUC, SetProjectMemberUC

router = APIRouter(dependencies=[Depends(require_server_mode)])

_KINDS = ("user", "group")


def _actor() -> Actor:
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return actor


def _principal(raw: str) -> tuple[str, str]:
    """`user:<id>` или `group:<id>`: вид участника входит в путь, чтобы id людей и групп не пересекались."""
    kind, _, principal_id = raw.partition(":")
    if kind not in _KINDS or not principal_id:
        raise IdentityError(IdentityErrorCode.input_invalid)
    return kind, principal_id


_access_sort = sort_param(allowed=ACCESS_SORTS, default="name")


@router.get("/projects/{project_id}/members", response_model=ProjectAccessPage)
async def list_project_access(
    project_id: UUID,
    request: Request,
    response: Response,
    params: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Depends(search_param)],
    sort: Annotated[SortKey, Depends(_access_sort)],
    kind: Annotated[list[ProjectMemberKind] | None, Query()] = None,
    role: Annotated[list[ProjectRoleName] | None, Query()] = None,
) -> ProjectAccessPage:
    """Панель «Доступ»: видит любой участник проекта. Владелец и организация-владелец всегда первыми."""
    response.headers["Cache-Control"] = "no-store"
    query = AccessQuery(
        q=q, kinds=tuple(kind or ()), roles=tuple(Role(r) for r in role or ()), sort=sort, window=params.window
    )
    found = await (await request.state.dishka_container.get(ListProjectAccessUC)).execute(project_id, query)
    return ProjectAccessPage(
        items=[
            ProjectAccessEntry(
                subject_kind=r.subject_kind,
                subject_id=r.subject_id,
                name=r.name,
                detail=r.detail,
                role=r.role.value,
                locked=r.locked,
            )
            for r in found.items
        ],
        total=found.total,
        limit=params.limit,
        offset=params.offset,
    )


@router.get("/projects/{project_id}/members/candidates", response_model=ProjectAccessCandidateList)
async def list_access_candidates(
    project_id: UUID,
    request: Request,
    response: Response,
    params: Annotated[PickerParams, Depends(picker_params)],
    kind: ProjectMemberKind | None = None,
) -> ProjectAccessCandidateList:
    """Кого можно добавить: только люди и группы из общих организаций, по всей установке не перебрать."""
    response.headers["Cache-Control"] = "no-store"
    uc = await request.state.dishka_container.get(ListAccessCandidatesUC)
    found = await uc.execute(_actor(), project_id, params.q or "", limit=params.limit, kind=kind)
    return ProjectAccessCandidateList(
        items=[
            ProjectAccessCandidate(subject_kind=c.subject_kind, subject_id=c.subject_id, name=c.name, detail=c.detail)
            for c in found.items
        ],
        has_more=found.has_more,
    )


@router.get("/projects/{project_id}/transfer-candidates", response_model=PickerList)
async def list_transfer_candidates(
    project_id: UUID,
    request: Request,
    response: Response,
    params: Annotated[PickerParams, Depends(picker_params)],
    kind: Literal["user", "org"] | None = None,
) -> PickerList:
    """Кому передать проект: организации, где смотрящий владелец или админ, и люди общих организаций.

    Организацию адресует slug. Чужих людей и организаций по всей установке не перебрать.
    """
    response.headers["Cache-Control"] = "no-store"
    uc = await request.state.dishka_container.get(ListTransferCandidatesUC)
    found = await uc.execute(_actor(), project_id, params.q or "", limit=params.limit, kind=kind)
    return PickerList(
        items=[PickerItem(kind=c.kind, id=c.id, name=c.name, detail=c.detail) for c in found.items],
        has_more=found.has_more,
    )


@router.put("/projects/{project_id}/members/{principal}", response_model=ProjectMember)
async def set_project_member(
    project_id: UUID, principal: str, body: SetProjectMemberRequest, request: Request
) -> ProjectMember:
    kind, principal_id = _principal(principal)
    grant = ProjectMemberGrant(
        principal_kind="group" if kind == "group" else "user",
        principal_id=principal_id,
        role=Role(body.role),
        persona=body.persona,
        can_share=body.can_share,
        show_sources=body.show_sources,
        can_edit_all=body.can_edit_all,
    )
    uc = await request.state.dishka_container.get(SetProjectMemberUC)
    view = await uc.execute(_actor(), project_id, grant)
    return ProjectMember(
        kind=view.grant.principal_kind,
        principal_id=view.grant.principal_id,
        name=view.name,
        role=body.role,
        persona=view.grant.persona,
        can_share=view.grant.can_share,
        show_sources=view.grant.show_sources,
        can_edit_all=view.grant.can_edit_all,
    )


@router.delete("/projects/{project_id}/members/{principal}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_project_member(project_id: UUID, principal: str, request: Request) -> Response:
    kind, principal_id = _principal(principal)
    uc = await request.state.dishka_container.get(RemoveProjectMemberUC)
    await uc.execute(_actor(), project_id, kind, principal_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
