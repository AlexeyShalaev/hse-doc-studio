"""Единый движок очистки: прогоняет источники реестра, считает сроки из настроек и пишет статистику."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog

from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.lifecycle.policies import POLICY_BY_KEY, LifecyclePolicy, Strategy, effective_days
from hse_doc_studio.core.lifecycle.ports import (
    ILifecycleRuns,
    ILifecycleSource,
    PurgeContext,
    PurgeResult,
    SourceSize,
)

logger = structlog.get_logger(__name__)

ENGINE_STRATEGIES = frozenset({Strategy.partition_drop, Strategy.delete_batches, Strategy.file_sweep})


@dataclass
class ProcessCounters:
    """Счётчики этого процесса для /metrics (постоянная статистика прогонов лежит в БД)."""

    removed: int = 0
    partitions_dropped: int = 0
    errors: int = 0
    last_run_ts: float = 0.0
    size: SourceSize | None = None


@dataclass(frozen=True)
class LifecycleRunOutcome:
    key: str
    removed: int
    partitions_dropped: int
    more: bool
    error: str | None = None


class LifecycleEngine:
    """Идемпотентный прогон: повтор после сбоя или параллельный запуск с другим процессом ничего не ломает.

    Лидерство держит раннер фоновых задач, а кнопка «очистить сейчас» может пересечься с плановым прогоном; для
    этого пары `DELETE ... LIMIT` и `DROP` безопасны: повторное удаление того же ничего не находит.
    """

    def __init__(
        self,
        sources: Mapping[str, ILifecycleSource],
        settings: IInstanceSettingsRepository,
        runs: ILifecycleRuns,
        audit: IAuditLog,
        *,
        env_days: Mapping[str, int],
        batch_size: int,
        budget_s: float,
        clock: Clock = utc_now,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sources = dict(sources)
        self._settings = settings
        self._runs = runs
        self._audit = audit
        self._env_days = dict(env_days)
        self._batch = batch_size
        self._budget = budget_s
        self._clock = clock
        self._monotonic = monotonic
        self._locks = {key: asyncio.Lock() for key in self._sources}
        self.counters: dict[str, ProcessCounters] = {key: ProcessCounters() for key in self._sources}

    @property
    def keys(self) -> list[str]:
        return list(self._sources)

    def source(self, key: str) -> ILifecycleSource | None:
        return self._sources.get(key)

    async def days_for(self, policy: LifecyclePolicy, stored: Mapping[str, object] | None = None) -> int | None:
        values = stored if stored is not None else await self._settings.get_all()
        return effective_days(policy, values, self._env_days.get(policy.key))

    async def run_all(self) -> list[LifecycleRunOutcome]:
        stored = await self._settings.get_all()
        return [
            await self._run(key, stored) for key in self._sources if POLICY_BY_KEY[key].strategy in ENGINE_STRATEGIES
        ]

    async def run_one(self, key: str) -> LifecycleRunOutcome:
        return await self._run(key, await self._settings.get_all())

    async def _run(self, key: str, stored: Mapping[str, object]) -> LifecycleRunOutcome:
        policy = POLICY_BY_KEY[key]
        source = self._sources[key]
        now = self._clock()
        days = effective_days(policy, stored, self._env_days.get(key))
        cutoff: datetime | None = None if days is None else now - timedelta(days=days)
        ctx = PurgeContext(now=now, cutoff=cutoff, batch_size=self._batch, deadline=self._monotonic() + self._budget)
        started = self._monotonic()
        error: str | None = None
        result = PurgeResult()
        async with self._locks[key]:
            try:
                result = await source.purge(ctx)
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"[:500]
                logger.exception("lifecycle_source_failed", key=key)
        duration_ms = int((self._monotonic() - started) * 1000)
        counters = self.counters[key]
        counters.removed += result.removed
        counters.partitions_dropped += result.partitions_dropped
        counters.errors += 1 if error else 0
        counters.last_run_ts = now.timestamp()
        try:
            counters.size = await source.measure()
        except Exception:
            logger.warning("lifecycle_measure_failed", key=key)
        try:
            await self._runs.record(key, at=now, duration_ms=duration_ms, removed=result.removed, error=error)
        except Exception:
            logger.exception("lifecycle_stat_not_saved", key=key)
        if key == "audit_log" and error is None and (result.removed or result.partitions_dropped):
            await self._audit.record(
                "audit.purged",
                actor_id=None,
                details={"count": result.removed, "partitions": result.partitions_dropped, "keep_days": days},
            )
        if result.removed or result.partitions_dropped:
            logger.info(
                "lifecycle_purged",
                key=key,
                removed=result.removed,
                partitions=result.partitions_dropped,
                more=result.more,
                duration_ms=duration_ms,
            )
        return LifecycleRunOutcome(key, result.removed, result.partitions_dropped, result.more, error)
