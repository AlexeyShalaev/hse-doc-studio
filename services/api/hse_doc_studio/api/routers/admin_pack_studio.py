"""`/api/admin/pack-studio*`: включение Студии шаблонов и право «Автор шаблонов» людям и группам (D4)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.schemas.pack_studio import (
    CreatePackStudioGrantRequest,
    PackStudioAdminResponse,
    PackStudioGrantResponse,
    UpdatePackStudioAdminRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.entities import GrantSubjectKind, PackStudioGrant
from hse_doc_studio.use_cases.pack_studio.admin import PackStudioAdminUC, PackStudioAdminView

router = APIRouter()

_NO_STORE = {"Cache-Control": "no-store"}


async def _uc(request: Request) -> PackStudioAdminUC:
    return await request.state.dishka_container.get(PackStudioAdminUC)


def grant_response(grant: PackStudioGrant) -> PackStudioGrantResponse:
    return PackStudioGrantResponse(
        id=str(grant.id),
        subject=grant.subject.value,
        subject_id=grant.subject_id,
        name=grant.name,
        email=grant.email,
        org_slug=grant.org_slug,
        org_name=grant.org_name,
        granted_by=grant.granted_by,
        created_at=grant.created_at,
    )


def admin_response(view: PackStudioAdminView) -> PackStudioAdminResponse:
    return PackStudioAdminResponse(
        enabled=view.section.enabled,
        locked=view.section.locked,
        grants=[grant_response(grant) for grant in view.grants],
    )


async def get_pack_studio(request: Request, response: Response) -> PackStudioAdminResponse:
    response.headers.update(_NO_STORE)
    return admin_response(await (await _uc(request)).view(require_actor()))


async def put_pack_studio(request: Request, body: UpdatePackStudioAdminRequest) -> PackStudioAdminResponse:
    return admin_response(await (await _uc(request)).set_enabled(require_actor(), body.enabled))


async def add_grant(request: Request, body: CreatePackStudioGrantRequest) -> PackStudioGrantResponse:
    kind, subject = (
        (GrantSubjectKind.user, body.user_id) if body.user_id is not None else (GrantSubjectKind.group, body.group_id)
    )
    return grant_response(await (await _uc(request)).grant(require_actor(), kind, subject or ""))


async def remove_grant(request: Request, grant_id: UUID) -> Response:
    await (await _uc(request)).revoke(require_actor(), grant_id)
    return Response(status_code=204)


router.add_api_route("/pack-studio", get_pack_studio, methods=["GET"], response_model=PackStudioAdminResponse)
router.add_api_route("/pack-studio", put_pack_studio, methods=["PUT"], response_model=PackStudioAdminResponse)
router.add_api_route(
    "/pack-studio/grants", add_grant, methods=["POST"], status_code=201, response_model=PackStudioGrantResponse
)
router.add_api_route("/pack-studio/grants/{grant_id}", remove_grant, methods=["DELETE"], status_code=204)
