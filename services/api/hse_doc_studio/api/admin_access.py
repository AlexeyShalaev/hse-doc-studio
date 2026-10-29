"""Ограничение админки по host/IP: `/admin`, `/api/admin` и её чанк `/assets/admin-*`.

Чужому отвечаем 404, как будто админки нет. Без ограничений в настройках слой не ставится.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from hse_doc_studio.api.config import Settings, settings
from hse_doc_studio.api.identity_errors import identity_error_body
from hse_doc_studio.api.observability.client_ip import client_ip
from hse_doc_studio.core.identity.admin_access import AdminAccessPolicy
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode

logger = structlog.get_logger(__name__)

_PREFIXES = ("/api/admin", "/admin")
_ASSET_PREFIX = "/assets/admin-"


def is_admin_path(path: str) -> bool:
    if path.startswith(_ASSET_PREFIX):
        return True
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in _PREFIXES)


def request_allowed(policy: AdminAccessPolicy, request: Request, trusted_proxies: list[str]) -> bool:
    if not policy.restricted:
        return True
    return policy.allows(request.headers.get("host"), client_ip(request, trusted_proxies))


def admin_request_allowed(request: Request) -> bool:
    """Открыта ли админка для этого запроса по настройкам host/IP (признак `capabilities.admin`)."""
    return request_allowed(settings.admin.policy, request, settings.auth.trusted_proxies)


class AdminAccessMiddleware:
    def __init__(self, app: ASGIApp, *, policy: AdminAccessPolicy, trusted_proxies: list[str]) -> None:
        self.app = app
        self._policy = policy
        self._trusted_proxies = trusted_proxies

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not is_admin_path(scope["path"]):
            await self.app(scope, receive, send)
            return
        if request_allowed(self._policy, Request(scope), self._trusted_proxies):
            await self.app(scope, receive, send)
            return
        body = identity_error_body(IdentityError(IdentityErrorCode.not_found))
        await JSONResponse(body, status_code=404)(scope, receive, send)


def install_admin_access(app: FastAPI, cfg: Settings) -> None:
    policy = cfg.admin.policy
    if not policy.restricted:
        return
    logger.info(
        "admin is restricted",
        hosts=list(policy.hosts),
        networks=[str(net) for net in policy.networks],
    )
    app.add_middleware(AdminAccessMiddleware, policy=policy, trusted_proxies=list(cfg.auth.trusted_proxies))
