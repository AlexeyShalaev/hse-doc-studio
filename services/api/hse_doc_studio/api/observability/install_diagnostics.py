"""Самодиагностика: плановая проверка под лидерским локом, метрики hse_diag_* и публичный лёгкий эндпоинт."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse

from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.observability.diagnostics_metrics import diagnostics_collector
from hse_doc_studio.api.observability.metrics import MetricsRegistry
from hse_doc_studio.core.background import PeriodicTask
from hse_doc_studio.core.diagnostics.entities import DiagStatus, overall

if TYPE_CHECKING:
    from dishka import AsyncContainer


def build_public_router(container: AsyncContainer) -> APIRouter:
    """Без входа и без секретов: общий итог и статус каждой проверки, без причин, значений и адресов."""
    from hse_doc_studio.use_cases.diagnostics.service import DiagnosticsService  # noqa: PLC0415

    router = APIRouter(tags=["health"], include_in_schema=False)

    @router.get("/health/diagnostics")
    async def diagnostics() -> JSONResponse:
        service = await container.get(DiagnosticsService)
        states = await service.snapshot()
        results = [s.result for s in states.values()]
        headers = {"Cache-Control": "no-store"}
        if not results:
            return JSONResponse({"status": "unknown", "checks": {}}, status_code=503, headers=headers)
        total = overall(results, service.accepted)
        body = {
            "status": total.name,
            "checked_at": max(r.checked_at for r in results).isoformat(),
            "checks": {
                r.check_id: "accepted" if r.check_id in service.accepted else r.status.name
                for r in sorted(results, key=lambda r: r.check_id)
            },
        }
        code = 503 if total is DiagStatus.fail else 200
        return JSONResponse(body, status_code=code, headers=headers)

    return router


def install_diagnostics(app: FastAPI, container: AsyncContainer, cfg: Settings, metrics: MetricsRegistry) -> None:
    from hse_doc_studio.infra.di.providers.server_diagnostics import BackgroundHolder  # noqa: PLC0415
    from hse_doc_studio.use_cases.diagnostics.service import DiagnosticsService  # noqa: PLC0415

    diag = cfg.diagnostics

    async def _tick() -> None:
        await (await container.get(DiagnosticsService)).tick()

    if diag.enabled:
        app.state.background.register(
            PeriodicTask(name="diagnostics", interval_s=diag.interval_s, run=_tick, run_on_start=True)
        )
    if diag.public_endpoint:
        app.include_router(build_public_router(container))

    @app.on_event("startup")
    async def _diagnostics_startup() -> None:
        (await container.get(BackgroundHolder)).runner = app.state.background
        service = await container.get(DiagnosticsService)
        metrics.add_collector(
            diagnostics_collector(lambda: {k: v.result for k, v in service.last.items()}, lambda: service.accepted)
        )
