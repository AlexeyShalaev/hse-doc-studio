"""`/api/admin/pack-studio*`: включение Студии шаблонов и право «Автор шаблонов» людям и группам (D4)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response

from hse_doc_studio.api.routers.v1.pack_studio import official_repo_response
from hse_doc_studio.api.schemas.pack_studio import (
    CreatePackServiceAccessRequest,
    CreatePackStudioGrantRequest,
    PackServiceAccessCheckResponse,
    PackServiceAccessResponse,
    PackStudioAdminResponse,
    PackStudioGrantResponse,
    PackStudioOfficialAdminResponse,
    UpdatePackStudioAdminRequest,
    UpdatePackStudioOfficialRequest,
)
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.pack_studio.entities import GrantSubjectKind, PackStudioGrant
from hse_doc_studio.core.pack_studio.protocols import ServiceAccess
from hse_doc_studio.use_cases.pack_studio.admin import PackStudioAdminUC, PackStudioAdminView, ServiceAccessCheck
from hse_doc_studio.use_cases.pack_studio.official import OfficialAdminView

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
        fork_mode=access.fork_mode,
        fork_url=access.fork_url,
    )


async def list_service_access(request: Request, response: Response) -> list[PackServiceAccessResponse]:
    response.headers.update(_NO_STORE)
    return [service_access_response(a) for a in await (await _uc(request)).service_accesses(require_actor())]


async def add_service_access(request: Request, body: CreatePackServiceAccessRequest) -> PackServiceAccessResponse:
    """Служебный доступ репозитория паков (4.2): токен уровня установки, секрет назад не отдаётся."""
    access = await (await _uc(request)).add_service_access(
        require_actor(), url=body.url, token=body.token, label=body.label, fork_mode=body.fork_mode
    )
    return service_access_response(access)


def check_response(check: ServiceAccessCheck) -> PackServiceAccessCheckResponse:
    return PackServiceAccessCheckResponse(
        access=service_access_response(check.access),
        ok=check.ok,
        login=check.login,
        scopes=None if check.scopes is None else list(check.scopes),
        can_push=check.can_push,
        problems=[problem.value for problem in check.problems],
    )


async def check_service_access(request: Request, access_id: UUID) -> PackServiceAccessCheckResponse:
    """Срез T22: чей токен и его области, право push, у бота форк (находится или создаётся и запоминается)."""
    return check_response(await (await _uc(request)).check_service_access(require_actor(), access_id))


def official_admin_response(view: OfficialAdminView) -> PackStudioOfficialAdminResponse:
    return PackStudioOfficialAdminResponse(
        repo=official_repo_response(view.repo),
        bot_enabled=view.settings.enabled,
        daily_limit=view.settings.daily_limit,
        default_daily_limit=view.default_daily_limit,
        service_access=None if view.service_access is None else service_access_response(view.service_access),
    )


async def get_official(request: Request, response: Response) -> PackStudioOfficialAdminResponse:
    response.headers.update(_NO_STORE)
    return official_admin_response(await (await _uc(request)).official(require_actor()))


async def put_official(request: Request, body: UpdatePackStudioOfficialRequest) -> PackStudioOfficialAdminResponse:
    view = await (await _uc(request)).update_official(
        require_actor(), bot_enabled=body.bot_enabled, daily_limit=body.daily_limit
    )
    return official_admin_response(view)


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
router.add_api_route(
    "/pack-studio/service-access/{access_id}/check",
    check_service_access,
    methods=["POST"],
    response_model=PackServiceAccessCheckResponse,
)
router.add_api_route(
    "/pack-studio/official", get_official, methods=["GET"], response_model=PackStudioOfficialAdminResponse
)
router.add_api_route(
    "/pack-studio/official", put_official, methods=["PUT"], response_model=PackStudioOfficialAdminResponse
)
