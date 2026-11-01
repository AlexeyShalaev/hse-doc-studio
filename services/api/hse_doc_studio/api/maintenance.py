"""Режим обслуживания: 503 на всё, что ходит в базу, кроме `/health` и открытого статуса `/api/maintenance`."""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

STATUS_PATH = "/api/maintenance"
RESTORE_PREFIX = "/api/admin/backups/restore"
_OPEN_PATHS = {"/health", STATUS_PATH}
RETRY_AFTER_S = "30"


class MaintenanceMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        controller = getattr(scope.get("app") and scope["app"].state, "maintenance", None)
        if scope["type"] not in {"http", "websocket"} or controller is None:
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        if scope["type"] == "http" and path == STATUS_PATH:
            await JSONResponse(controller.status(), headers={"Cache-Control": "no-store"})(scope, receive, send)
            return
        if not controller.active or not (path.startswith("/api/") or path.startswith("/health")):
            await self.app(scope, receive, send)
            return
        if path in _OPEN_PATHS or (path.startswith(RESTORE_PREFIX) and not controller.writing):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1013})
            return
        body = {"detail": "the service is in maintenance mode", "code": "maintenance"}
        await JSONResponse(body, status_code=503, headers={"Retry-After": RETRY_AFTER_S})(scope, receive, send)
