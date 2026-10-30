"""Подключение наблюдаемости и фоновых задач к приложению.

``install_health`` ставится в любом режиме (в local готовность просто «ok»), остальное только в server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.observability.health import HealthRegistry, build_health_router, build_metrics_router
from hse_doc_studio.api.observability.metrics import MetricsMiddleware, MetricsRegistry, background_collector
from hse_doc_studio.api.observability.request_id import RequestIdMiddleware
from hse_doc_studio.core.background import BackgroundTaskRunner, PeriodicTask

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = structlog.get_logger()


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


def install_blob_gc(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Периодическая сборка мусора блобов входа задач; регистрируется до старта раннера."""
    from hse_doc_studio.use_cases.storage.gc_blobs import GcBlobsUC  # noqa: PLC0415

    async def _gc() -> None:
        await (await container.get(GcBlobsUC)).run()

    app.state.background.register(PeriodicTask(name="blob_gc", interval_s=cfg.server.blob_gc_interval_s, run=_gc))


def install_project_usage(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Периодическое измерение места проектов и сборка сирот (папки тома и префиксы S3 без записи в projects)."""
    from hse_doc_studio.infra.projects.orphan_gc import OrphanGc  # noqa: PLC0415 — sqlalchemy только с extra server
    from hse_doc_studio.infra.projects.usage_meter import ProjectUsageSweeper  # noqa: PLC0415

    async def _measure() -> None:
        await (await container.get(ProjectUsageSweeper)).run()

    async def _orphans() -> None:
        await (await container.get(OrphanGc)).run()

    app.state.background.register(
        PeriodicTask(name="project_usage", interval_s=cfg.server.project_usage_interval_s, run=_measure)
    )
    app.state.background.register(
        PeriodicTask(name="orphan_gc", interval_s=cfg.server.orphan_gc_interval_s, run=_orphans)
    )


def install_job_retention(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Периодическая уборка выходов задач без владельца и устаревших терминальных записей с логами."""
    from hse_doc_studio.infra.jobs.retention import JobRetention  # noqa: PLC0415 — sqlalchemy только с extra server

    async def _retain() -> None:
        await (await container.get(JobRetention)).run()

    app.state.background.register(
        PeriodicTask(name="job_retention", interval_s=cfg.server.job_retention_interval_s, run=_retain)
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


def install_bucket_cors(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """На старте выставляет CORS бакета, если заданы источники: без него pdf.js не читает PDF по ссылке с Range."""
    if not cfg.s3.cors_origins:
        return

    @app.on_event("startup")
    async def _apply_cors() -> None:
        from hse_doc_studio.core.storage import IObjectStore, ObjectStoreError  # noqa: PLC0415
        from hse_doc_studio.infra.storage.s3 import S3ObjectStore  # noqa: PLC0415

        store = await container.get(IObjectStore)
        if not isinstance(store, S3ObjectStore):
            return
        try:
            await store.apply_cors(cfg.s3.cors_origins)
        except ObjectStoreError as exc:
            logger.warning("bucket cors not applied", exc=str(exc))


def install_object_store_health(app: FastAPI, container: AsyncContainer, health: HealthRegistry) -> None:
    """Проверка «s3» для /health/ready и экрана окружения мастера: бакет (или каталог) доступен."""
    from hse_doc_studio.core.storage import IObjectStore  # noqa: PLC0415

    async def _probe() -> str | None:
        await (await container.get(IObjectStore)).check()
        return None

    health.register("s3", _probe)


def install_service_pool_health(app: FastAPI, container: AsyncContainer, health: HealthRegistry, cfg: Settings) -> None:
    """Проверки «languagetool» и «onlyoffice» для экрана сервисов админа; регистрируются, только если реплики заданы."""
    from hse_doc_studio.core.office import IOfficeEditorService  # noqa: PLC0415
    from hse_doc_studio.infra.services.languagetool import LanguageToolProxy  # noqa: PLC0415

    if cfg.languagetool.pool_replicas:

        async def _languagetool() -> str | None:
            proxy = await container.get(LanguageToolProxy)
            return None if await proxy.probe() else "no_healthy_replica"

        health.register("languagetool", _languagetool, optional=True)

    if cfg.office_editor.pool_replicas:

        async def _onlyoffice() -> str | None:
            editor = await container.get(IOfficeEditorService)
            return None if await editor.ensure_running() else "no_healthy_replica"

        health.register("onlyoffice", _onlyoffice, optional=True)


def install_runner_health(app: FastAPI, container: AsyncContainer, health: HealthRegistry) -> None:
    """Проверка «runners» для экрана окружения мастера: необязательная, на свежей установке без раннеров
    `/health/ready` остаётся зелёным, а мастер показывает причину."""
    from hse_doc_studio.core.identity.session_policy import utc_now  # noqa: PLC0415
    from hse_doc_studio.core.jobs.admin import RunnerStatus, runner_status  # noqa: PLC0415
    from hse_doc_studio.core.jobs.routing import RunnerScope  # noqa: PLC0415
    from hse_doc_studio.core.jobs.runners import IRunnerRepository  # noqa: PLC0415

    async def _runners() -> str | None:
        # Личные раннеры не обслуживают общую очередь: здоровье установки считаем только по общим.
        active = [
            r
            for r in await (await container.get(IRunnerRepository)).list()
            if r.revoked_at is None and r.scope is RunnerScope.shared
        ]
        if not active:
            return "no_runners"
        now = utc_now()
        return None if any(runner_status(r, now) is RunnerStatus.online for r in active) else "no_online_runner"

    health.register("runners", _runners, optional=True)


def install_job_reaper(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Периодический возврат задач с истёкшей арендой и контроль таймаутов; идёт только у лидера."""
    from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService  # noqa: PLC0415

    async def _sweep() -> None:
        await (await container.get(JobQueueService)).sweep()

    app.state.background.register(PeriodicTask(name="job_reaper", interval_s=cfg.jobs.reaper_interval_s, run=_sweep))


def install_runner_pairings_purge(app: FastAPI, container: AsyncContainer) -> None:
    """Периодическая чистка устаревших сопряжений раннера по коду устройства; идёт только у лидера."""
    from hse_doc_studio.use_cases.jobs.pairing import RunnerPairingService  # noqa: PLC0415

    async def _purge_pairings() -> None:
        # Сопряжения по коду живут 10 минут, записи старше суток больше не нужны.
        await (await container.get(RunnerPairingService)).purge()

    app.state.background.register(PeriodicTask(name="runner_pairings_purge", interval_s=600.0, run=_purge_pairings))
