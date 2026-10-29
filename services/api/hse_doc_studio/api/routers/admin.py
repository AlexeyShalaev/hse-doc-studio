"""Каркас `/api/admin`: гард и фабрика роутера. Маршруты добавляют срезы админки поверх use cases других зон."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from hse_doc_studio.api.actor import resolve_actor
from hse_doc_studio.api.admin_access import admin_request_allowed
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.rate_limit import rate_limit_guard
from hse_doc_studio.api.routers import admin_audit, admin_runners, admin_settings, admin_users
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.mode import StudioMode

ADMIN_API_PREFIX = "/api/admin"


async def admin_guard(request: Request) -> None:
    """Аноним получает 401, любой не админ и любой запрос с чужого host/IP получает 404: админки для них нет."""
    if settings.mode is StudioMode.local or not admin_request_allowed(request):
        raise IdentityError(IdentityErrorCode.not_found)
    actor = await resolve_actor(request)
    if not actor.is_instance_admin:
        raise IdentityError(IdentityErrorCode.not_found)
    set_current_actor(actor)


def make_admin_router() -> APIRouter:
    router = APIRouter(prefix=ADMIN_API_PREFIX, dependencies=[Depends(admin_guard), Depends(rate_limit_guard)])
    router.include_router(admin_users.router)
    router.include_router(admin_audit.router)
    router.include_router(admin_settings.router)
    router.include_router(admin_runners.router)
    return router
