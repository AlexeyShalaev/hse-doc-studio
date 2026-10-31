"""Использование квот: `GET /api/v1/usage` (человек и его организации), `GET /api/v1/orgs/{slug}/usage`.

Только сервер. Чужая организация и несуществующая неразличимы (404).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from hse_doc_studio.api.actor import require_server_mode
from hse_doc_studio.api.schemas.quotas import MyUsageResponse, OwnerUsageResponse
from hse_doc_studio.api.usage_view import owner_usage_view
from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.use_cases.admin.ops_quotas import QuotaService
from hse_doc_studio.use_cases.quotas.usage import GetMyUsageUC, GetOrgUsageUC

router = APIRouter(dependencies=[Depends(require_server_mode)])

_NO_STORE = {"Cache-Control": "no-store"}


@router.get("/usage", response_model=MyUsageResponse)
async def my_usage(request: Request, response: Response) -> MyUsageResponse:
    response.headers.update(_NO_STORE)
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    container = request.state.dishka_container
    usage = await (await container.get(GetMyUsageUC)).execute(actor)
    warn = (await (await container.get(QuotaService)).snapshot()).policy.warn_percent
    return MyUsageResponse(
        user=owner_usage_view(usage.user), orgs=[owner_usage_view(o) for o in usage.orgs], warn_percent=warn
    )


@router.get("/orgs/{slug}/usage", response_model=OwnerUsageResponse)
async def org_usage(slug: str, request: Request, response: Response) -> OwnerUsageResponse:
    response.headers.update(_NO_STORE)
    actor = current_actor()
    if actor is None:
        raise IdentityError(IdentityErrorCode.auth_required)
    return owner_usage_view(await (await request.state.dishka_container.get(GetOrgUsageUC)).execute(actor, slug))
