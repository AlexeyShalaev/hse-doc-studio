"""Маршруты серверного режима вне `/api/v1`: протокол раннера и админка. В локальном режиме отвечают 404."""

from __future__ import annotations

from fastapi import FastAPI

from hse_doc_studio.api.routers import admin_api, runner_api


def include_server_routers(app: FastAPI) -> None:
    app.include_router(runner_api.router)
    app.include_router(admin_api.router)
