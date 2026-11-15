"""`/api/admin/pack-studio*`: включение Студии шаблонов и право «Автор шаблонов» людям и группам (D4)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.schemas.pack_studio import (
    CreatePackServiceAccessRequest,
    CreatePackStudioGrantRequest,
    PackServiceAccessResponse,
    PackStudioAdminResponse,
    PackStudioGrantResponse,
    UpdatePackStudioAdminRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.entities import GrantSubjectKind, PackStudioGrant
from hse_doc_studio.core.pack_studio.protocols import ServiceAccess
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


def service_access_response(access: ServiceAccess) -> PackServiceAccessResponse:
    return PackServiceAccessResponse(
        id=str(access.id),
        url=access.url,
        label=access.label,
        token_family=access.token_family,
        created_by=access.created_by,
        created_by_name=access.created_by_name,
        created_at=access.created_at,
    )


async def list_service_access(request: Request, response: Response) -> list[PackServiceAccessResponse]:
    response.headers.update(_NO_STORE)
    return [service_access_response(a) for a in await (await _uc(request)).service_accesses(require_actor())]


async def add_service_access(request: Request, body: CreatePackServiceAccessRequest) -> PackServiceAccessResponse:
    """Служебный доступ репозитория паков (4.2): токен уровня установки, секрет назад не отдаётся."""
    access = await (await _uc(request)).add_service_access(
        require_actor(), url=body.url, token=body.token, label=body.label
    )
    return service_access_response(access)


async def remove_service_access(request: Request, access_id: UUID) -> Response:
    await (await _uc(request)).remove_service_access(require_actor(), access_id)
    return Response(status_code=204)


router.add_api_route("/pack-studio", get_pack_studio, methods=["GET"], response_model=PackStudioAdminResponse)
router.add_api_route("/pack-studio", put_pack_studio, methods=["PUT"], response_model=PackStudioAdminResponse)
router.add_api_route(
    "/pack-studio/grants", add_grant, methods=["POST"], status_code=201, response_model=PackStudioGrantResponse
)
router.add_api_route("/pack-studio/grants/{grant_id}", remove_grant, methods=["DELETE"], status_code=204)
router.add_api_route(
    "/pack-studio/service-access",
    list_service_access,
    methods=["GET"],
    response_model=list[PackServiceAccessResponse],
)
router.add_api_route(
    "/pack-studio/service-access",
    add_service_access,
    methods=["POST"],
    status_code=201,
    response_model=PackServiceAccessResponse,
)
router.add_api_route(
    "/pack-studio/service-access/{access_id}", remove_service_access, methods=["DELETE"], status_code=204
)
