"""Автомасштабирование раннеров: цикл сверки очереди с числом раннеров, состояние для админки, правка политики."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog, IInstanceSettingsRepository
from hse_doc_studio.core.identity.session_policy import Clock, utc_now
from hse_doc_studio.core.jobs.autoscale import (
    KEY_PREFIX,
    AutoscaleMode,
    AutoscalePolicy,
    AutoscaleState,
    IQueueMetricsReader,
    IRunnerOrchestrator,
    OrchestratorError,
    QueueMetrics,
    ScaleAction,
    ScaleDecision,
    ScaleRequest,
    decide,
    policy_from,
    policy_to_settings,
)
from hse_doc_studio.core.uow import IUnitOfWork
from hse_doc_studio.use_cases.admin.users import require_admin
from hse_doc_studio.use_cases.identity.auth_settings import SOURCE_ADMIN

logger = structlog.get_logger()

KEY_LAST_UP = KEY_PREFIX + "last_up_at"
KEY_LAST_DOWN = KEY_PREFIX + "last_down_at"


class IOrchestratorFactory(Protocol):
    def create(self, policy: AutoscalePolicy) -> IRunnerOrchestrator | None: ...


@dataclass(frozen=True)
class ScaleOutcome:
    at: datetime
    desired: int
    ok: bool
    error: str | None = None


@dataclass(frozen=True)
class AutoscaleStatus:
    policy: AutoscalePolicy
    metrics: QueueMetrics
    decision: ScaleDecision
    last_outcome: ScaleOutcome | None
    last_up_at: datetime | None
    last_down_at: datetime | None
    orchestrator_current: int | None
    evaluated_at: datetime


def _when(value: object) -> datetime | None:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


class AutoscaleService:
    """Один экземпляр на процесс (цикл идёт под замком лидера). Память хранит последнее решение и окно простоя."""

    def __init__(
        self,
        repo: IInstanceSettingsRepository,
        metrics: IQueueMetricsReader,
        factory: IOrchestratorFactory,
        audit: IAuditLog,
        *,
        clock: Clock = utc_now,
    ) -> None:
        self._repo = repo
        self._metrics = metrics
        self._factory = factory
        self._audit = audit
        self._clock = clock
        self._idle_since: datetime | None = None
        self._last_outcome: ScaleOutcome | None = None
        # Последние метрики и решение: из них собирается экспозиция для внешних скейлеров (KEDA и подобные).
        self.last_seen: tuple[QueueMetrics, ScaleDecision] | None = None

    async def _load(self) -> tuple[AutoscalePolicy, AutoscaleState]:
        values = await self._repo.get_all()
        state = AutoscaleState(
            last_up_at=_when(values.get(KEY_LAST_UP)),
            last_down_at=_when(values.get(KEY_LAST_DOWN)),
            idle_since=self._idle_since,
        )
        return policy_from(values), state

    async def evaluate(self) -> AutoscaleStatus:
        """Решение по текущей нагрузке без исполнения (для админки и сухих прогонов)."""
        policy, state = await self._load()
        now = self._clock()
        metrics = await self._metrics.read(now)
        decision, _ = decide(policy, metrics, state, now)
        self.last_seen = (metrics, decision)
        orchestrator = self._factory.create(policy)
        current = await orchestrator.current() if orchestrator is not None else None
        return AutoscaleStatus(
            policy, metrics, decision, self._last_outcome, state.last_up_at, state.last_down_at, current, now
        )

    async def tick(self) -> ScaleDecision:
        """Один проход цикла: решение, и если оно требует действия и режим не `off`, вызов оркестратора."""
        policy, state = await self._load()
        now = self._clock()
        metrics = await self._metrics.read(now)
        decision, new_state = decide(policy, metrics, state, now)
        self._idle_since = new_state.idle_since
        self.last_seen = (metrics, decision)
        orchestrator = self._factory.create(policy)
        if decision.action is ScaleAction.hold or orchestrator is None or policy.mode is AutoscaleMode.off:
            return decision
        request = ScaleRequest(decision.desired, decision.current, decision.reason.value, metrics, now)
        try:
            await orchestrator.scale_to(request)
        except OrchestratorError as exc:
            logger.warning("autoscale: orchestrator refused", desired=decision.desired, error=str(exc))
            self._last_outcome = ScaleOutcome(now, decision.desired, False, str(exc)[:300])
            return decision
        self._last_outcome = ScaleOutcome(now, decision.desired, True)
        key = KEY_LAST_UP if decision.action is ScaleAction.up else KEY_LAST_DOWN
        await self._repo.set(key, now.isoformat(), source="system")
        if decision.action is ScaleAction.up:
            self._idle_since = None
        await self._audit.record(
            "autoscale.scaled",
            actor_id=None,
            details={
                "from": decision.current,
                "to": decision.desired,
                "reason": decision.reason.value,
                "queued": metrics.queued,
                "running": metrics.running,
            },
        )
        return decision


class GetAutoscaleUC:
    def __init__(self, service: AutoscaleService) -> None:
        self._service = service

    async def execute(self, actor: Actor) -> AutoscaleStatus:
        require_admin(actor)
        return await self._service.evaluate()


class UpdateAutoscaleUC:
    def __init__(
        self, repo: IInstanceSettingsRepository, audit: IAuditLog, uow: IUnitOfWork, service: AutoscaleService
    ) -> None:
        self._repo = repo
        self._audit = audit
        self._uow = uow
        self._service = service

    async def execute(self, actor: Actor, new: AutoscalePolicy) -> AutoscaleStatus:
        """Полная замена политики. Диапазоны проверил сам `AutoscalePolicy`."""
        admin_id = require_admin(actor)
        before = policy_from(await self._repo.get_all())
        async with self._uow.begin():
            for key, value in policy_to_settings(new).items():
                if value is None:
                    await self._repo.delete(key)
                else:
                    await self._repo.set(key, value, source=SOURCE_ADMIN)
            if policy_to_settings(before) != policy_to_settings(new):
                await self._audit.record(
                    "settings.autoscale_update",
                    actor_id=admin_id,
                    details={"before": _loggable(before), "after": _loggable(new)},
                )
        return await self._service.evaluate()


def _loggable(policy: AutoscalePolicy) -> dict[str, object | None]:
    values = policy_to_settings(policy)
    # Адрес webhook может нести ключ в строке запроса: в журнал идёт только признак.
    values[f"{KEY_PREFIX}webhook_url"] = bool(policy.webhook_url)
    return values
