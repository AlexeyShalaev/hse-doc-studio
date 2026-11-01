"""Админка «Хранение данных»: обзор источников, правка сроков, запуск очистки, пороги места."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.errors import IdentityError, IdentityErrorCode
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.lifecycle.disk import (
    CRITICAL_RANGE,
    KEY_CRITICAL_PERCENT,
    KEY_WARN_PERCENT,
    WARN_RANGE,
    SafeMode,
    StorageLevel,
    StorageThresholds,
    effective_thresholds,
)
from hse_doc_studio.core.lifecycle.policies import POLICIES, POLICY_BY_KEY, LifecyclePolicy
from hse_doc_studio.core.lifecycle.ports import ILifecycleRuns, ILifecycleSource, RunStat, SourceSize, VolumeUsage
from hse_doc_studio.core.settings_scope import SOURCE_ADMIN
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.lifecycle.engine import ENGINE_STRATEGIES, LifecycleEngine, LifecycleRunOutcome
from hse_doc_studio.use_cases.lifecycle.guard import StorageGuard


@dataclass(frozen=True)
class TaskRun:
    """Итог собственной периодической задачи (раннер фоновых задач держит его в памяти лидера)."""

    runs: int
    failures: int
    last_run_at: datetime | None


@dataclass(frozen=True)
class SourceView:
    policy: LifecyclePolicy
    days: int | None
    days_source: str  # admin | env | default | fixed
    size: SourceSize | None
    last_run: RunStat | None
    task: TaskRun | None


@dataclass(frozen=True)
class VolumeView:
    usage: VolumeUsage
    level: StorageLevel


@dataclass(frozen=True)
class LifecycleOverview:
    sources: list[SourceView]
    volumes: list[VolumeView]
    thresholds: StorageThresholds
    level: StorageLevel
    safe_mode: bool


TaskStatsReader = Callable[[], Mapping[str, TaskRun]]


class GetLifecycleUC:
    def __init__(
        self,
        engine: LifecycleEngine,
        settings: IInstanceSettingsRepository,
        runs: ILifecycleRuns,
        guard: StorageGuard,
        safe_mode: SafeMode,
        task_stats: TaskStatsReader,
    ) -> None:
        self._engine = engine
        self._settings = settings
        self._runs = runs
        self._guard = guard
        self._safe = safe_mode
        self._task_stats = task_stats

    async def execute(self, actor: Actor) -> LifecycleOverview:
        require_admin(actor)
        stored = await self._settings.get_all()
        runs = await self._runs.all()
        tasks = self._task_stats()
        views: list[SourceView] = []
        for policy in POLICIES:
            source = self._engine.source(policy.key)
            size = await _safe_measure(source) if source is not None else None
            days = await self._engine.days_for(policy, stored)
            views.append(
                SourceView(
                    policy=policy,
                    days=days,
                    days_source=_days_source(policy, stored, days),
                    size=size,
                    last_run=runs.get(policy.key),
                    task=tasks.get(policy.task) if policy.task else None,
                )
            )
        thresholds = effective_thresholds(stored)
        usage = await self._guard.snapshot()
        volumes = [VolumeView(v, thresholds.level(v.used_ratio)) for v in usage]
        level = max((v.level for v in volumes), default=StorageLevel.ok)
        return LifecycleOverview(views, volumes, thresholds, level, self._safe.active)


async def _safe_measure(source: ILifecycleSource) -> SourceSize | None:
    try:
        return await source.measure()
    except Exception:
        return None


def _days_source(policy: LifecyclePolicy, stored: Mapping[str, object], days: int | None) -> str:
    if policy.bounds is None:
        return "fixed"
    if policy.setting_key is not None and policy.setting_key in stored and days == stored[policy.setting_key]:
        return "admin"
    return "env" if policy.env is not None and days != policy.bounds.default_days else "default"


class UpdateRetentionUC:
    """Срок хранения источника в границах реестра. `days=None` снимает правку: дальше действует умолчание."""

    def __init__(self, settings: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._settings = settings
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, key: str, days: int | None) -> None:
        admin_id = require_admin(actor)
        policy = POLICY_BY_KEY.get(key)
        if policy is None:
            raise IdentityError(IdentityErrorCode.not_found)
        if not policy.editable or policy.bounds is None or policy.setting_key is None:
            raise IdentityError(IdentityErrorCode.input_invalid)
        if days is not None and not policy.bounds.contains(days):
            raise IdentityError(IdentityErrorCode.input_invalid)
        async with self._uow.begin():
            if days is None:
                await self._settings.delete(policy.setting_key)
            else:
                await self._settings.set(policy.setting_key, days, source=SOURCE_ADMIN)
            await self._audit.record("settings.retention_update", actor_id=admin_id, target=key, details={"days": days})


class UpdateThresholdsUC:
    def __init__(self, settings: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork) -> None:
        self._settings = settings
        self._audit = audit
        self._uow = uow

    async def execute(self, actor: Actor, warn_percent: int, critical_percent: int) -> None:
        admin_id = require_admin(actor)
        if not (
            WARN_RANGE[0] <= warn_percent <= WARN_RANGE[1]
            and CRITICAL_RANGE[0] <= critical_percent <= CRITICAL_RANGE[1]
        ):
            raise IdentityError(IdentityErrorCode.input_invalid)
        if critical_percent <= warn_percent:
            raise IdentityError(IdentityErrorCode.input_invalid)
        async with self._uow.begin():
            await self._settings.set(KEY_WARN_PERCENT, warn_percent, source=SOURCE_ADMIN)
            await self._settings.set(KEY_CRITICAL_PERCENT, critical_percent, source=SOURCE_ADMIN)
            await self._audit.record(
                "settings.storage_thresholds_update",
                actor_id=admin_id,
                details={"warn_percent": warn_percent, "critical_percent": critical_percent},
            )


class RunLifecycleUC:
    """Кнопка «очистить сейчас»: тот же прогон, что по расписанию, только для одного источника и только безопасный."""

    def __init__(self, engine: LifecycleEngine, audit: IAuditLog) -> None:
        self._engine = engine
        self._audit = audit

    async def execute(self, actor: Actor, key: str) -> LifecycleRunOutcome:
        admin_id = require_admin(actor)
        policy = POLICY_BY_KEY.get(key)
        if policy is None or self._engine.source(key) is None:
            raise IdentityError(IdentityErrorCode.not_found)
        if policy.strategy not in ENGINE_STRATEGIES or not policy.run_now:
            raise IdentityError(IdentityErrorCode.forbidden)
        outcome = await self._engine.run_one(key)
        await self._audit.record(
            "lifecycle.run_now",
            actor_id=admin_id,
            target=key,
            details={"removed": outcome.removed, "partitions": outcome.partitions_dropped, "error": outcome.error},
        )
        return outcome


def epoch_to_datetime(value: float | None) -> datetime | None:
    return datetime.fromtimestamp(value, tz=UTC) if value else None
