"""Участники проекта на сервере: роль человеку или группе и её снятие. Правит владелец проекта."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.schemas.session import ProjectMember, SetProjectMemberRequest
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor, Role
from hse_doc_studio.core.access.repositories import ProjectMemberGrant
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
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
