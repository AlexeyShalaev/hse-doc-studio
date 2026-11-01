"""Адрес клонирования проекта по git (раздел 7.6): для настроек проекта на сервере."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.schemas.git_remote import ProjectGitRemote
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.git_remote.projects import GetProjectGitRemoteUC

router = APIRouter(dependencies=[Depends(require_server_mode)])


@router.get("/projects/{project_id}/git-remote", response_model=ProjectGitRemote)
async def get_project_git_remote(project_id: UUID, request: Request) -> ProjectGitRemote:
    uc: GetProjectGitRemoteUC = await request.state.dishka_container.get(GetProjectGitRemoteUC)
    try:
        view = await uc.execute(require_actor(), project_id)
    except NotFoundError:
        raise IdentityError(IdentityErrorCode.not_found) from None
    return ProjectGitRemote(enabled=view.enabled, clone_url=view.clone_url, can_push=view.can_push, branch=view.branch)
