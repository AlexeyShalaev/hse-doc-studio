"""Фоновые задачи жизненного цикла данных: очистка по реестру политик и проба места на томах."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from fastapi import FastAPI

from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.observability.lifecycle_metrics import lifecycle_collector
from hse_doc_studio.api.observability.metrics import MetricsRegistry
from hse_doc_studio.core.background import BackgroundTaskRunner, PeriodicTask
from hse_doc_studio.core.lifecycle.disk import PROCESS_SAFE_MODE
from hse_doc_studio.use_cases.lifecycle.admin import TaskRun

if TYPE_CHECKING:
    from dishka import AsyncContainer

logger = structlog.get_logger()


def _task_runs_reader(background: BackgroundTaskRunner) -> Callable[[], dict[str, TaskRun]]:
    def read() -> dict[str, TaskRun]:
        return {
            name: TaskRun(
                runs=stat.runs,
                failures=stat.failures,
                last_run_at=datetime.fromtimestamp(stat.last_run_at, tz=UTC) if stat.last_run_at else None,
            )
            for name, stat in background.stats().items()
        }

    return read


def install_data_lifecycle(app: FastAPI, container: AsyncContainer, cfg: Settings, metrics: MetricsRegistry) -> None:
    """Регистрирует задачи до старта раннера: очистка и проба идут только у лидера.

    Партиции создаются при старте любого экземпляра, не только лидера: запись в журнал не должна упасть из-за
    того, что лидер давно не работал.
    """
    background = app.state.background

    @app.on_event("startup")
    async def _lifecycle_startup() -> None:
        from hse_doc_studio.infra.di.providers.server_lifecycle import TaskStatsHolder  # noqa: PLC0415
        from hse_doc_studio.infra.lifecycle.sql_sources import PartitionedTableSource  # noqa: PLC0415
        from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine  # noqa: PLC0415
        from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard  # noqa: PLC0415
        from hse_doc_studio.use_cases.lifecycle.sweep import LifecycleSweepService  # noqa: PLC0415

        engine = await container.get(LifecycleEngine)
        for key in ("audit_log", "ai_usage"):
            source = engine.source(key)
            if isinstance(source, PartitionedTableSource):
                await source.ensure_partitions()
        (await container.get(TaskStatsHolder)).reader = _task_runs_reader(background)
        guard = await container.get(StorageGuard)
        sweeps = await container.get(LifecycleSweepService)
        metrics.add_collector(
            lifecycle_collector(lambda: engine.counters, lambda: guard.last, PROCESS_SAFE_MODE, lambda: sweeps.finished)
        )

    @app.on_event("shutdown")
    async def _lifecycle_shutdown() -> None:
        """Идущий здесь прогон «Освободить место» закрывается как прерванный сразу, а не через 5 минут."""
        from hse_doc_studio.use_cases.lifecycle.sweep import LifecycleSweepService  # noqa: PLC0415

        try:
            await (await container.get(LifecycleSweepService)).aclose()
        except Exception:
            logger.warning("lifecycle_sweep_close_failed", exc_info=True)

    _register(background, container, cfg)


def _register(background: BackgroundTaskRunner, container: AsyncContainer, cfg: Settings) -> None:
    from hse_doc_studio.use_cases.lifecycle.engine import LifecycleEngine  # noqa: PLC0415
    from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard  # noqa: PLC0415
    from hse_doc_studio.use_cases.lifecycle.sweep import LifecycleSweepService  # noqa: PLC0415

    life = cfg.lifecycle

    async def _run() -> None:
        # Прогон «Освободить место», чья реплика пропала, закрывается здесь, даже если экран никто не открывает.
        await (await container.get(LifecycleSweepService)).reap()
        await (await container.get(LifecycleEngine)).run_all()

    async def _probe() -> None:
        await (await container.get(StorageGuard)).tick()

    if life.enabled:
        background.register(
            PeriodicTask(name="data_lifecycle", interval_s=life.interval_s, run=_run, run_on_start=True)
        )
    if life.probe_enabled:
        background.register(
            PeriodicTask(name="storage_guard", interval_s=life.probe_interval_s, run=_probe, run_on_start=True)
        )
