"""Где идут сборки проекта (`/api/v1/projects/{id}/build-runners`, только сервер).

Читать может любой участник проекта, менять только владелец личного проекта (гард по `PROJECT_SETTINGS`).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.schemas.personal_runners import (
    OwnerRunnerChip,
    ProjectBuildRunners,
    UpdateProjectBuildRunnersRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.jobs.routing import ProjectBuildRunners as BuildRunnersPolicy
from hse_doc_studio.use_cases.jobs.project_build_runners import ProjectBuildRunnersService, ProjectBuildRunnersView

router = APIRouter(dependencies=[Depends(require_server_mode)])


def _view(view: ProjectBuildRunnersView) -> ProjectBuildRunners:
    return ProjectBuildRunners(
        policy=view.policy.value,
        editable=view.editable,
        project_kind="personal" if view.personal_project else "org",
        personal_runners_enabled=view.personal_runners_enabled,
        my_builds=view.my_builds.value,
        wait_s=view.wait_s,
        owner_runners=[OwnerRunnerChip(name=chip.name, state=chip.state.value) for chip in view.owner_runners],
    )


async def _service(request: Request) -> ProjectBuildRunnersService:
    return await request.state.dishka_container.get(ProjectBuildRunnersService)


@router.get("/projects/{project_id}/build-runners", response_model=ProjectBuildRunners)
async def get_build_runners(project_id: UUID, request: Request, response: Response) -> ProjectBuildRunners:
    response.headers["Cache-Control"] = "no-store"
    return _view(await (await _service(request)).view(require_actor(), project_id))


@router.put("/projects/{project_id}/build-runners", response_model=ProjectBuildRunners)
async def put_build_runners(
    project_id: UUID, body: UpdateProjectBuildRunnersRequest, request: Request
) -> ProjectBuildRunners:
    service = await _service(request)
    return _view(await service.set_policy(require_actor(), project_id, BuildRunnersPolicy(body.policy)))
