"""Подключение наблюдаемости и фоновых задач к приложению.

``install_health`` ставится в любом режиме (в local готовность просто «ok»), остальное только в server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.observability.health import HealthRegistry, build_health_router, build_metrics_router
from hse_doc_studio.api.observability.metrics import MetricsMiddleware, MetricsRegistry, background_collector
from hse_doc_studio.api.observability.request_id import RequestIdMiddleware
from hse_doc_studio.core.background import BackgroundTaskRunner, PeriodicTask

if TYPE_CHECKING:
    from dishka import AsyncContainer


def install_health(app: FastAPI, cfg: Settings, registry: HealthRegistry | None = None) -> HealthRegistry:
    registry = registry or HealthRegistry()
    token = cfg.observability.health_token
    app.include_router(build_health_router(registry, health_token=token.get_secret_value() if token else None))
    return registry


def install_server_observability(app: FastAPI, cfg: Settings, health: HealthRegistry) -> MetricsRegistry:
    """Request id, метрики и /metrics; middleware добавляется последним, значит оборачивает всё остальное."""
    metrics = MetricsRegistry()
    token = cfg.observability.metrics_token
    app.include_router(build_metrics_router(metrics, metrics_token=token.get_secret_value() if token else None))
    app.add_middleware(MetricsMiddleware, registry=metrics)
    app.add_middleware(RequestIdMiddleware)
    return metrics


def install_background(
    app: FastAPI,
    container: AsyncContainer,
    health: HealthRegistry,
    metrics: MetricsRegistry,
    *,
    shutdown_timeout_s: float,
) -> BackgroundTaskRunner:
    """Раннер периодики с лидерством через Postgres и проверкой БД в /health/ready.

    Серверные срезы регистрируют свои задачи через ``app.state.background.register(...)`` до старта.
    """
    from sqlalchemy import text  # noqa: PLC0415 — sqlalchemy есть только с extra server
    from sqlalchemy.ext.asyncio import AsyncEngine  # noqa: PLC0415

    from hse_doc_studio.infra.db.leader import PgAdvisoryLeaderLock  # noqa: PLC0415

    runner = BackgroundTaskRunner()
    app.state.background = runner
    metrics.add_collector(background_collector(runner))

    async def _db_probe() -> str | None:
        engine = await container.get(AsyncEngine)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return None

    health.register("database", _db_probe)

    @app.on_event("startup")
    async def _background_startup() -> None:
        engine = await container.get(AsyncEngine)
        runner.use_leader_lock(PgAdvisoryLeaderLock(engine))
        runner.start()

    @app.on_event("shutdown")
    async def _background_shutdown() -> None:
        await runner.stop(shutdown_timeout_s)

    return runner


def install_project_purge(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Периодическое стирание удалённых проектов по сроку хранения; регистрируется до старта раннера."""
    from hse_doc_studio.infra.projects.purge import ProjectPurger  # noqa: PLC0415 — sqlalchemy только с extra server

    async def _purge() -> None:
        await (await container.get(ProjectPurger)).purge_expired()

    app.state.background.register(
        PeriodicTask(name="project_purge", interval_s=cfg.server.project_purge_interval_s, run=_purge)
    )


def install_auth_cleanup(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Периодическая чистка просроченных сессий, токенов, писем outbox и счётчиков входов."""
    from hse_doc_studio.use_cases.identity.housekeeping import AuthCleanupService  # noqa: PLC0415

    async def _cleanup() -> None:
        await (await container.get(AuthCleanupService)).run()

    app.state.background.register(
        PeriodicTask(name="auth_cleanup", interval_s=cfg.server.auth_cleanup_interval_s, run=_cleanup)
    )


def install_audit_retention(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Периодическое стирание событий аудита старше срока хранения (единственный путь стирания журнала)."""
    from hse_doc_studio.use_cases.admin.audit import PurgeAuditUC  # noqa: PLC0415

    async def _purge() -> None:
        await (await container.get(PurgeAuditUC)).execute()

    app.state.background.register(
        PeriodicTask(name="audit_retention", interval_s=cfg.server.audit_purge_interval_s, run=_purge)
    )
