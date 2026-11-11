"""Подключение наблюдаемости и фоновых задач к приложению.

``install_health`` ставится в любом режиме (в local готовность просто «ok»), остальное только в server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.observability.health import HealthRegistry, build_health_router, build_metrics_router
from hse_doc_studio.api.observability.mail_metrics import mail_collector
from hse_doc_studio.api.observability.metrics import MetricsMiddleware, MetricsRegistry, background_collector
from hse_doc_studio.api.observability.request_id import RequestIdMiddleware
from hse_doc_studio.core.background import BackgroundTaskRunner, PeriodicTask
from hse_doc_studio.core.jobs.control import COMMANDS_REAPER_INTERVAL_S
from hse_doc_studio.use_cases.mail.dispatch import MAIL_COUNTERS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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
    metrics.add_collector(mail_collector(MAIL_COUNTERS))
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


_HOUSEKEEPING_INTERVAL_S = 6 * 3600.0


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


def install_quota_housekeeping(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Периодическая уборка старых периодов счётчиков квот и журнала вызовов ИИ-шлюза."""
    from hse_doc_studio.use_cases.quotas.housekeeping import QuotaHousekeeping  # noqa: PLC0415

    async def _clean() -> None:
        await (await container.get(QuotaHousekeeping)).run()

    app.state.background.register(
        PeriodicTask(name="quota_housekeeping", interval_s=_HOUSEKEEPING_INTERVAL_S, run=_clean)
    )


def install_autoscale(app: FastAPI, container: AsyncContainer, cfg: Settings, metrics: MetricsRegistry) -> None:
    """Цикл автомасштабирования раннеров и метрики очереди для внешних скейлеров; регистрируется до старта раннера."""
    from hse_doc_studio.api.observability.autoscale_metrics import autoscale_collector  # noqa: PLC0415
    from hse_doc_studio.use_cases.jobs.autoscale import AutoscaleService  # noqa: PLC0415

    async def _tick() -> None:
        await (await container.get(AutoscaleService)).tick()

    app.state.background.register(PeriodicTask(name="autoscale", interval_s=cfg.autoscale.interval_s, run=_tick))

    @app.on_event("startup")
    async def _autoscale_metrics() -> None:
        service = await container.get(AutoscaleService)
        metrics.add_collector(autoscale_collector(lambda: service.last_seen))


def _install_backup_provision(app: FastAPI, container: AsyncContainer, cfg: Settings) -> None:
    """Начальная настройка бэкапов из окружения (Helm, compose): один раз на пустой установке, под лидерским локом."""
    if cfg.backups.provision.destination_kind == "none":
        return

    async def _provision() -> None:
        from hse_doc_studio.use_cases.backup.provision import ProvisionBackupUC, build_plan  # noqa: PLC0415

        p = cfg.backups.provision

        def reveal(value: object) -> str | None:
            return value.get_secret_value() if value is not None else None  # type: ignore[attr-defined]

        plan = build_plan(
            kind=p.destination_kind,
            name=p.name,
            local_path=p.local_path,
            endpoint=p.endpoint,
            region=p.region,
            bucket=p.bucket,
            prefix=p.prefix,
            path_style=p.path_style,
            access_key=reveal(p.access_key),
            secret_key=reveal(p.secret_key),
            schedule_enabled=p.schedule_enabled,
            schedule_kind=p.schedule_kind,
            interval_hours=p.interval_hours,
            cron=p.cron,
            keep_last=p.keep_last,
            keep_days=p.keep_days,
            encryption_mode=p.encryption_mode,
            passphrase=reveal(p.passphrase),
            notify_admins=p.notify_admins,
        )
        await (await container.get(ProvisionBackupUC)).execute(plan)

    app.state.background.register(
        PeriodicTask(name="backup_provision", interval_s=365 * 86400.0, run=_provision, run_on_start=True)
    )


def _install_maintenance(app: FastAPI, container: AsyncContainer) -> None:
    """Режим обслуживания для восстановления из админки: ответ 503 на `/api` и подхват метки прерванной записи."""
    from hse_doc_studio.api.maintenance import MaintenanceMiddleware  # noqa: PLC0415
    from hse_doc_studio.core.backup.protocols import IMaintenanceMode  # noqa: PLC0415
    from hse_doc_studio.infra.backup.maintenance import MaintenanceController  # noqa: PLC0415

    app.add_middleware(MaintenanceMiddleware)

    @app.on_event("startup")
    async def _maintenance_startup() -> None:
        controller = await container.get(IMaintenanceMode)
        assert isinstance(controller, MaintenanceController)  # noqa: S101
        controller.bind(app.state.background)
        await controller.adopt_marker()
        app.state.maintenance = controller


def _backup_metrics_refresh(
    container: AsyncContainer, metrics: MetricsRegistry | None
) -> Callable[[], Awaitable[None]]:
    """Снимок метрик бэкапов и его обновление из таблицы запусков."""
    from hse_doc_studio.api.observability.backup_metrics import backup_collector  # noqa: PLC0415
    from hse_doc_studio.use_cases.backup.metrics import BackupMetricsRefresher, BackupMetricsState  # noqa: PLC0415

    state = BackupMetricsState()
    if metrics is not None:
        metrics.add_collector(backup_collector(state))

    async def _refresh() -> None:
        from hse_doc_studio.core.backup.protocols import IBackupRunRepository  # noqa: PLC0415
        from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository  # noqa: PLC0415

        refresher = BackupMetricsRefresher(
            state, await container.get(IBackupRunRepository), await container.get(IInstanceSettingsRepository)
        )
        try:
            await refresher.refresh()
        except Exception:
            logger.warning("backup metrics refresh failed", exc_info=True)

    return _refresh


def install_backups(
    app: FastAPI, container: AsyncContainer, cfg: Settings, metrics: MetricsRegistry | None = None
) -> None:
    """Планировщик бэкапов под лидерским локом; прерванные запуски прошлого процесса закрываются на старте."""
    if not cfg.backups.enabled:
        return
    from hse_doc_studio.use_cases.backup.runs import ScheduledBackupTick  # noqa: PLC0415
    from hse_doc_studio.use_cases.backup.service import BackupService  # noqa: PLC0415

    refresh_metrics = _backup_metrics_refresh(container, metrics)

    async def _tick() -> None:
        await (await container.get(ScheduledBackupTick)).run_once()
        await refresh_metrics()

    app.state.background.register(PeriodicTask(name="backup_schedule", interval_s=cfg.backups.tick_s, run=_tick))

    @app.on_event("startup")
    async def _recover_backup_runs() -> None:
        recovered = await (await container.get(BackupService)).recover_stale()
        if recovered:
            logger.warning("backup runs interrupted by a restart", count=recovered)
        await refresh_metrics()

    _install_backup_provision(app, container, cfg)
    _install_maintenance(app, container)

    @app.on_event("shutdown")
    async def _stop_backups() -> None:
        await (await container.get(BackupService)).cancel_all()


def install_server_updates(app: FastAPI, container: AsyncContainer, cfg: Settings, metrics: MetricsRegistry) -> None:
    """Планировщик автообновления под лидерским локом и метрики `hse_update_*`."""
    if not cfg.server_update.enabled:
        return
    from hse_doc_studio.api.observability.update_metrics import update_collector  # noqa: PLC0415
    from hse_doc_studio.use_cases.server_update.service import UpdateService  # noqa: PLC0415

    async def _tick() -> None:
        await (await container.get(UpdateService)).tick()

    app.state.background.register(PeriodicTask(name="server_update", interval_s=cfg.server_update.tick_s, run=_tick))

    @app.on_event("startup")
    async def _update_metrics() -> None:
        service = await container.get(UpdateService)
        metrics.add_collector(update_collector(lambda: service.snapshot))


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
    """Периодический возврат задач с истёкшей арендой, контроль таймаутов и снятие задач без подходящего раннера;
    идёт только у лидера."""
    from hse_doc_studio.use_cases.jobs.queue_service import JobQueueService  # noqa: PLC0415
    from hse_doc_studio.use_cases.jobs.stranded import StrandedJobSweeper  # noqa: PLC0415

    async def _sweep() -> None:
        await (await container.get(JobQueueService)).sweep()
        await (await container.get(StrandedJobSweeper)).sweep()

    app.state.background.register(PeriodicTask(name="job_reaper", interval_s=cfg.jobs.reaper_interval_s, run=_sweep))


def install_runner_commands_reaper(app: FastAPI, container: AsyncContainer, metrics: MetricsRegistry) -> None:
    """Команды раннерам: не забранные за 10 минут становятся `expired`, без хода 3 минуты или у отозванного и
    ушедшего раннера `lost` (storage-cleanup.md, 5.3); идёт только у лидера. Чтение команды проверяет то же.

    Тот же тик обновляет метрику `hse_runner_disk_cleanable_bytes` по проекции последних замеров.
    """
    from hse_doc_studio.api.observability.runner_disk_metrics import runner_disk_collector  # noqa: PLC0415
    from hse_doc_studio.use_cases.jobs.runner_control import RunnerControlService  # noqa: PLC0415
    from hse_doc_studio.use_cases.jobs.runner_disk import RunnerDiskMetrics, RunnerDiskUC  # noqa: PLC0415

    async def _reap() -> None:
        await (await container.get(RunnerControlService)).settle()
        try:
            await (await container.get(RunnerDiskUC)).refresh_metrics()
        except Exception:
            logger.warning("runner disk metrics refresh failed", exc_info=True)

    app.state.background.register(
        PeriodicTask(name="runner_commands_reaper", interval_s=COMMANDS_REAPER_INTERVAL_S, run=_reap)
    )

    @app.on_event("startup")
    async def _runner_disk_metrics() -> None:
        metrics.add_collector(runner_disk_collector(await container.get(RunnerDiskMetrics)))


def install_runner_pairings_purge(app: FastAPI, container: AsyncContainer) -> None:
    """Периодическая чистка устаревших сопряжений раннера по коду устройства; идёт только у лидера."""
    from hse_doc_studio.use_cases.jobs.pairing import RunnerPairingService  # noqa: PLC0415

    async def _purge_pairings() -> None:
        # Сопряжения по коду живут 10 минут, записи старше суток больше не нужны.
        await (await container.get(RunnerPairingService)).purge()

    app.state.background.register(PeriodicTask(name="runner_pairings_purge", interval_s=600.0, run=_purge_pairings))


def install_device_authorizations_purge(app: FastAPI, container: AsyncContainer) -> None:
    """Чистка входов устройств по коду (git сервера): записи старше суток больше не нужны."""
    from hse_doc_studio.use_cases.identity.device_flow import DeviceFlowService  # noqa: PLC0415

    async def _purge() -> None:
        await (await container.get(DeviceFlowService)).purge()

    app.state.background.register(PeriodicTask(name="device_authorizations_purge", interval_s=600.0, run=_purge))
