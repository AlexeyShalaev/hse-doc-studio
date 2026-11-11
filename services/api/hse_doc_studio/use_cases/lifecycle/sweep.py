"""«Освободить место»: предпросмотр по текущим срокам и прогон всех ручных источников движка на сервере.

Прогон идёт задачей asyncio в реплике, принявшей запрос, а состояние живёт в Postgres (`ILifecycleSweeps`):
ход читает и останавливает любая реплика. Каждый шаг это `LifecycleEngine.run_one`, тот же прогон, что по кнопке
источника и по расписанию, с тем же бюджетом и замком. Сбой одного источника не мешает остальным.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable, Coroutine
from dataclasses import replace
from typing import Any
from uuid import uuid4

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.lifecycle.policies import POLICIES, POLICY_BY_KEY, Strategy
from hse_doc_studio.core.lifecycle.ports import ILifecycleSource
from hse_doc_studio.core.lifecycle.sweeps import (
    KEEP_SWEEPS,
    PREVIEW_CAP,
    STALE_AFTER,
    STEP_ERROR_MAX,
    ExcludedReason,
    ILifecycleSweeps,
    LifecycleSweep,
    PreviewSource,
    StepStatus,
    SweepPreview,
    SweepStatus,
    SweepStep,
    closed_steps,
)
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.lifecycle.engine import ENGINE_STRATEGIES, LifecycleEngine

logger = structlog.get_logger(__name__)

AUDIT_TARGET = "all"


def _excluded_reason(strategy: Strategy) -> ExcludedReason:
    if strategy in ENGINE_STRATEGIES:
        return ExcludedReason.protected
    return ExcludedReason(strategy.value)


async def _size(source: ILifecycleSource | None) -> int | None:
    if source is None:
        return None
    try:
        return (await source.measure()).bytes
    except Exception:
        logger.warning("lifecycle_measure_failed", key=source.key, exc_info=True)
        return None


class LifecycleSweepService:
    def __init__(
        self,
        engine: LifecycleEngine,
        sweeps: ILifecycleSweeps,
        settings: IInstanceSettingsRepository,
        audit: IAuditLog,
        *,
        clock: Clock = utc_now,
        new_id: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self._engine = engine
        self._sweeps = sweeps
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id
        self._tasks: set[asyncio.Task[None]] = set()
        # Итоги прогонов этого процесса для /metrics (`hse_lifecycle_sweeps_total{status}`).
        self.finished: Counter[str] = Counter()

    # ---- адреса 9.2 ------------------------------------------------------------------------------------------

    async def preview(self, actor: Actor) -> SweepPreview:
        require_admin(actor)
        stored = await self._settings.get_all()
        manual = self._engine.manual_keys()
        sources: list[PreviewSource] = []
        for key in manual:
            counted = await self._engine.count_expired(key, PREVIEW_CAP, stored)
            count = counted.count
            sources.append(
                PreviewSource(
                    key=key,
                    days=await self._engine.days_for(POLICY_BY_KEY[key], stored),
                    cutoff=counted.cutoff,
                    count=None if count is None else min(count, PREVIEW_CAP),
                    capped=count is not None and count > PREVIEW_CAP,
                    bytes=await _size(self._engine.source(key)),
                )
            )
        excluded = tuple((p.key, _excluded_reason(p.strategy)) for p in POLICIES if p.key not in manual)
        return SweepPreview(tuple(sources), excluded)

    async def current(self, actor: Actor) -> LifecycleSweep | None:
        require_admin(actor)
        await self.reap()
        return await self._sweeps.latest()

    async def start(self, actor: Actor) -> LifecycleSweep:
        admin_id = require_admin(actor)
        await self.reap()
        keys = self._engine.manual_keys()
        now = self._clock()
        sweep = LifecycleSweep(
            id=self._new_id(),
            status=SweepStatus.running,
            started_by=admin_id,
            started_at=now,
            updated_at=now,
            finished_at=None,
            steps=tuple(SweepStep(key) for key in keys),
        )
        if not await self._sweeps.create(sweep, keep=KEEP_SWEEPS):
            raise IdentityError(IdentityErrorCode.lifecycle_sweep_busy)
        await self._audit.record(
            "lifecycle.sweep", actor_id=admin_id, target=AUDIT_TARGET, details={"sweep_id": sweep.id, "sources": keys}
        )
        self._spawn(self._run(sweep))
        return sweep

    async def cancel(self, actor: Actor, sweep_id: str) -> LifecycleSweep:
        """Остановка после текущего источника: ведущая реплика увидит `cancelling` перед следующим шагом."""
        admin_id = require_admin(actor)
        await self.reap()
        sweep = await self._sweeps.request_cancel(sweep_id, at=self._clock())
        if sweep is None:
            raise IdentityError(IdentityErrorCode.not_found)
        if not sweep.status.active:
            raise IdentityError(IdentityErrorCode.command_finished)
        await self._audit.record(
            "lifecycle.sweep_cancel", actor_id=admin_id, target=AUDIT_TARGET, details={"sweep_id": sweep.id}
        )
        return sweep

    # ---- обслуживание ----------------------------------------------------------------------------------------

    async def reap(self) -> int:
        """Прогоны, чья реплика пропала (нет обновления дольше `STALE_AFTER`), закрываются как `interrupted`."""
        now = self._clock()
        closed = await self._sweeps.interrupt_stale(before=now - STALE_AFTER, at=now)
        for sweep in closed:
            await self._finished(sweep)
        return len(closed)

    async def drain(self) -> None:
        """Дождаться прогонов этого процесса (тесты и остановка)."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def aclose(self) -> None:
        """Остановка api: идущий прогон закрывается как `interrupted` сразу, а не через 5 минут."""
        for task in list(self._tasks):
            task.cancel()
        await self.drain()

    # ---- прогон ----------------------------------------------------------------------------------------------

    def _spawn(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, sweep: LifecycleSweep) -> None:
        steps = list(sweep.steps)
        try:
            status = await self._walk(sweep.id, steps)
        except asyncio.CancelledError:
            await asyncio.shield(self._close(sweep.id, SweepStatus.interrupted, steps))
            raise
        except Exception:
            logger.exception("lifecycle_sweep_failed", sweep_id=sweep.id)
            status = SweepStatus.error
        if status is not None:
            await self._close(sweep.id, status, steps)

    async def _walk(self, sweep_id: str, steps: list[SweepStep]) -> SweepStatus | None:
        """Шаги по порядку; `steps` обновляется на месте. None: прогон уже закрыт другой репликой."""
        for index, step in enumerate(steps):
            steps[index] = replace(step, status=StepStatus.running)
            current = await self._sweeps.save_steps(sweep_id, steps, at=self._clock())
            if current is None or not current.active:
                logger.warning("lifecycle_sweep_closed_elsewhere", sweep_id=sweep_id, status=current)
                return None
            if current is SweepStatus.cancelling:
                steps[index:] = [replace(s, status=StepStatus.skipped) for s in steps[index:]]
                return SweepStatus.cancelled
            steps[index] = await self._step(step.key)
        return SweepStatus.error if any(s.status is StepStatus.error for s in steps) else SweepStatus.done

    async def _close(self, sweep_id: str, status: SweepStatus, steps: list[SweepStep]) -> None:
        try:
            finished = await self._sweeps.finish(sweep_id, status, closed_steps(steps), at=self._clock())
        except Exception:
            # База недоступна: строка останется идущей и закроется как прерванная через `STALE_AFTER`.
            logger.exception("lifecycle_sweep_not_closed", sweep_id=sweep_id)
            return
        if finished is not None:
            await self._finished(finished)

    async def _step(self, key: str) -> SweepStep:
        source = self._engine.source(key)
        before = await _size(source)
        try:
            outcome = await self._engine.run_one(key)
        except Exception as exc:  # run_one ловит сбой источника сам; сюда попадает только поломка движка
            logger.exception("lifecycle_sweep_step_failed", key=key)
            error = f"{type(exc).__name__}: {exc}"[:STEP_ERROR_MAX]
            return SweepStep(key, StepStatus.error, bytes_before=before, error=error)
        error = outcome.error[:STEP_ERROR_MAX] if outcome.error else None
        return SweepStep(
            key=key,
            status=StepStatus.error if error else StepStatus.done,
            removed=outcome.removed,
            partitions_dropped=outcome.partitions_dropped,
            more=outcome.more,
            bytes_before=before,
            bytes_after=await _size(source),
            error=error,
        )

    async def _finished(self, sweep: LifecycleSweep) -> None:
        self.finished[sweep.status.value] += 1
        logger.info(
            "lifecycle_swept",
            sweep_id=sweep.id,
            status=sweep.status.value,
            removed=sweep.removed_total,
            freed_bytes=sweep.freed_bytes,
        )
        try:
            await self._audit.record(
                "lifecycle.swept",
                actor_id=sweep.started_by,
                target=AUDIT_TARGET,
                details={
                    "sweep_id": sweep.id,
                    "status": sweep.status.value,
                    "removed": sweep.removed_total,
                    "freed_bytes": sweep.freed_bytes,
                    "errors": sweep.errors,
                },
            )
        except Exception:
            logger.exception("lifecycle_swept_not_audited", sweep_id=sweep.id)
