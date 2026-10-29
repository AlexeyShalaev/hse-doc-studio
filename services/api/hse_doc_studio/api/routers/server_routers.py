"""Маршруты серверного режима вне `/api/v1`: протокол раннера и админка. В локальном режиме отвечают 404."""

from __future__ import annotations

from fastapi import FastAPI

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.routers import runner_api, services_api
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.mode import StudioMode


def include_server_routers(app: FastAPI) -> None:
    app.include_router(runner_api.router)
    app.include_router(services_api.router)
    if settings.mode is StudioMode.server:
        app.include_router(make_admin_router(), tags=["admin"])
