"""Маршруты серверного режима вне `/api/v1`: протокол раннера и админка. В локальном режиме отвечают 404."""

from __future__ import annotations

from fastapi import FastAPI

from hse_doc_studio.api.config import settings
from hse_doc_studio.api.routers import collab_ws, git_http, runner_api, runner_relay, services_api
from hse_doc_studio.api.routers.admin import make_admin_router
from hse_doc_studio.core.mode import StudioMode


def include_server_routers(app: FastAPI) -> None:
    app.include_router(runner_api.router)
    app.include_router(runner_relay.router)
    app.include_router(services_api.router)
    # Сокет совместной правки (этап 5); в локальном режиме закрывает соединение сам.
    app.include_router(collab_ws.router)
    # gitremote: git по HTTPS и /git/-/*; вне сервера и при выключенном git_remote отвечают 404.
    app.include_router(git_http.router)
    if settings.mode is StudioMode.server:
        app.include_router(make_admin_router(), tags=["admin"])
