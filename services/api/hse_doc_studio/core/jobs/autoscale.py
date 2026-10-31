"""Автомасштабирование общих раннеров: политика, метрики очереди и чистое решение «сколько раннеров нужно».

`decide` не знает ни об оркестраторе, ни о часах: время и метрики приходят аргументами, поэтому правила
проверяются без базы. Умеет масштабировать любой оркестратор за портом `IRunnerOrchestrator` (docker compose,
внешний webhook, Kubernetes через KEDA по метрикам); привязки к облаку вендора здесь нет.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol

KEY_PREFIX = "autoscale."
MAX_RUNNERS = 200


class AutoscaleMode(StrEnum):
    """`off`: только подсказка в админке. `webhook` и `compose`: решение исполняется оркестратором."""

    off = "off"
    webhook = "webhook"
    compose = "compose"


class ScaleAction(StrEnum):
    hold = "hold"
    up = "up"
    down = "down"


class ScaleReason(StrEnum):
    below_min = "below_min"
    above_max = "above_max"
    queue_depth = "queue_depth"
    queue_wait = "queue_wait"
    at_max = "at_max"
    cooldown_up = "cooldown_up"
    idle = "idle"
    idle_wait = "idle_wait"
    cooldown_down = "cooldown_down"
    at_min = "at_min"
    busy = "busy"
    balanced = "balanced"


class AutoscaleValueError(ValueError):
    """Значение политики вне допустимого; `field` называет поле запроса."""

    def __init__(self, field: str) -> None:
        super().__init__(f"autoscale value out of range: {field}")
        self.field = field


@dataclass(frozen=True)
class AutoscalePolicy:
    mode: AutoscaleMode = AutoscaleMode.off
    min_runners: int = 1
    max_runners: int = 4
    # Сколько ждущих задач на один слот допустимо до роста.
    target_queue_per_slot: float = 2.0
    # Сколько секунд старшая ждущая задача может ждать до роста.
    scale_up_wait_s: int = 30
    cooldown_up_s: int = 60
    cooldown_down_s: int = 300
    # Сколько секунд очередь должна быть пуста и раннеры свободны до уменьшения.
    idle_before_down_s: int = 300
    step_up: int = 2
    step_down: int = 1
    webhook_url: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.min_runners <= MAX_RUNNERS:
            raise AutoscaleValueError("min_runners")
        if not max(1, self.min_runners) <= self.max_runners <= MAX_RUNNERS:
            raise AutoscaleValueError("max_runners")
        if not 0.1 <= self.target_queue_per_slot <= 100:  # noqa: PLR2004
            raise AutoscaleValueError("target_queue_per_slot")
        self._check_seconds_and_steps()
        if self.mode is AutoscaleMode.webhook and not self.webhook_url:
            raise AutoscaleValueError("webhook_url")

    def _check_seconds_and_steps(self) -> None:
        for name in ("scale_up_wait_s", "cooldown_up_s", "cooldown_down_s", "idle_before_down_s"):
            if not 0 <= getattr(self, name) <= 86400:  # noqa: PLR2004
                raise AutoscaleValueError(name)
        for name in ("step_up", "step_down"):
            if not 1 <= getattr(self, name) <= MAX_RUNNERS:
                raise AutoscaleValueError(name)


@dataclass(frozen=True)
class QueueMetrics:
    """Нагрузка общего пула. Личные раннеры и задачи на них сюда не входят: общий пул они не расширяют."""

    queued: int = 0
    oldest_wait_s: float = 0.0
    running: int = 0
    runners_online: int = 0
    slots_total: int = 0

    @property
    def slots_busy(self) -> int:
        return min(self.running, self.slots_total) if self.slots_total else self.running

    @property
    def slots_per_runner(self) -> float:
        return self.slots_total / self.runners_online if self.runners_online else 1.0


@dataclass(frozen=True)
class AutoscaleState:
    last_up_at: datetime | None = None
    last_down_at: datetime | None = None
    # С какого момента очередь пуста и раннеры помещаются в меньший размер.
    idle_since: datetime | None = None


@dataclass(frozen=True)
class ScaleDecision:
    current: int
    desired: int
    action: ScaleAction
    reason: ScaleReason
    # Сколько секунд осталось до конца остывания, если оно удержало решение.
    wait_s: int = 0


def _remaining(since: datetime | None, window_s: int, now: datetime) -> int:
    if since is None:
        return 0
    return max(0, math.ceil(window_s - (now - since).total_seconds()))


def decide(
    policy: AutoscalePolicy, metrics: QueueMetrics, state: AutoscaleState, now: datetime
) -> tuple[ScaleDecision, AutoscaleState]:
    """Решение и новое состояние (меняется только `idle_since`; остывания фиксирует исполнитель после успеха)."""
    current = metrics.runners_online
    if current < policy.min_runners:
        return ScaleDecision(current, policy.min_runners, ScaleAction.up, ScaleReason.below_min), state
    if current > policy.max_runners:
        return ScaleDecision(current, policy.max_runners, ScaleAction.down, ScaleReason.above_max), state
    pressure = _pressure(policy, metrics)
    if pressure is not None:
        state = replace(state, idle_since=None)
        return _grow(policy, metrics, state, now, current, metrics.slots_per_runner, pressure), state
    return _shrink_or_hold(policy, metrics, state, now, current)


def _hold_reason(policy: AutoscalePolicy, metrics: QueueMetrics, current: int) -> ScaleReason:
    if metrics.queued > 0:
        return ScaleReason.balanced
    return ScaleReason.at_min if current <= policy.min_runners else ScaleReason.busy


def _shrink_or_hold(
    policy: AutoscalePolicy, metrics: QueueMetrics, state: AutoscaleState, now: datetime, current: int
) -> tuple[ScaleDecision, AutoscaleState]:
    # Свободно ли после уменьшения: идущие задачи помещаются в слоты оставшихся раннеров.
    smaller = max(policy.min_runners, current - policy.step_down)
    idle = (
        current > policy.min_runners and metrics.queued == 0 and metrics.running <= smaller * metrics.slots_per_runner
    )
    if not idle:
        state = replace(state, idle_since=None)
        return ScaleDecision(current, current, ScaleAction.hold, _hold_reason(policy, metrics, current)), state
    if state.idle_since is None:
        state = replace(state, idle_since=now)
    idle_wait = _remaining(state.idle_since, policy.idle_before_down_s, now)
    cooldown = max(
        _remaining(state.last_down_at, policy.cooldown_down_s, now),
        _remaining(state.last_up_at, policy.cooldown_down_s, now),
    )
    if idle_wait or cooldown:
        reason = ScaleReason.idle_wait if idle_wait >= cooldown else ScaleReason.cooldown_down
        return ScaleDecision(current, current, ScaleAction.hold, reason, max(idle_wait, cooldown)), state
    return ScaleDecision(current, smaller, ScaleAction.down, ScaleReason.idle), state


def _pressure(policy: AutoscalePolicy, metrics: QueueMetrics) -> ScaleReason | None:
    """Почему пора расти; `None`, если очередь справляется."""
    if metrics.queued <= 0:
        return None
    if metrics.runners_online == 0 or metrics.slots_total == 0:
        return ScaleReason.queue_depth
    if metrics.queued / metrics.slots_total > policy.target_queue_per_slot:
        return ScaleReason.queue_depth
    if metrics.oldest_wait_s >= policy.scale_up_wait_s:
        return ScaleReason.queue_wait
    return None


def _grow(  # noqa: PLR0913
    policy: AutoscalePolicy,
    metrics: QueueMetrics,
    state: AutoscaleState,
    now: datetime,
    current: int,
    per_runner: float,
    reason: ScaleReason,
) -> ScaleDecision:
    if current >= policy.max_runners:
        return ScaleDecision(current, current, ScaleAction.hold, ScaleReason.at_max)
    wait = _remaining(state.last_up_at, policy.cooldown_up_s, now)
    if wait:
        return ScaleDecision(current, current, ScaleAction.hold, ScaleReason.cooldown_up, wait)
    # Раннеров больше, чем задач, не нужно: хватает по одному слоту на каждую идущую и ждущую.
    useful = math.ceil((metrics.queued + metrics.running) / per_runner) if per_runner else policy.max_runners
    desired = min(policy.max_runners, current + policy.step_up, max(useful, current + 1))
    return ScaleDecision(current, desired, ScaleAction.up, reason)


def policy_to_settings(policy: AutoscalePolicy) -> dict[str, object | None]:
    """Ключи `instance_settings`; `None` значит «снять значение»."""
    return {
        f"{KEY_PREFIX}mode": policy.mode.value,
        f"{KEY_PREFIX}min": policy.min_runners,
        f"{KEY_PREFIX}max": policy.max_runners,
        f"{KEY_PREFIX}target_queue_per_slot": policy.target_queue_per_slot,
        f"{KEY_PREFIX}scale_up_wait_s": policy.scale_up_wait_s,
        f"{KEY_PREFIX}cooldown_up_s": policy.cooldown_up_s,
        f"{KEY_PREFIX}cooldown_down_s": policy.cooldown_down_s,
        f"{KEY_PREFIX}idle_before_down_s": policy.idle_before_down_s,
        f"{KEY_PREFIX}step_up": policy.step_up,
        f"{KEY_PREFIX}step_down": policy.step_down,
        f"{KEY_PREFIX}webhook_url": policy.webhook_url,
    }


def _int(values: Mapping[str, object], key: str, default: int) -> int:
    value = values.get(KEY_PREFIX + key)
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def policy_from(values: Mapping[str, object]) -> AutoscalePolicy:
    """Испорченная запись в базе читается как умолчание: цикл не должен падать из-за настройки."""
    base = AutoscalePolicy()
    raw_target = values.get(KEY_PREFIX + "target_queue_per_slot")
    target = (
        float(raw_target)
        if isinstance(raw_target, (int, float)) and not isinstance(raw_target, bool)
        else base.target_queue_per_slot
    )
    raw_mode = values.get(KEY_PREFIX + "mode")
    mode = AutoscaleMode(raw_mode) if isinstance(raw_mode, str) and raw_mode in AutoscaleMode else base.mode
    url = values.get(KEY_PREFIX + "webhook_url")
    try:
        return AutoscalePolicy(
            mode=mode,
            min_runners=_int(values, "min", base.min_runners),
            max_runners=_int(values, "max", base.max_runners),
            target_queue_per_slot=target,
            scale_up_wait_s=_int(values, "scale_up_wait_s", base.scale_up_wait_s),
            cooldown_up_s=_int(values, "cooldown_up_s", base.cooldown_up_s),
            cooldown_down_s=_int(values, "cooldown_down_s", base.cooldown_down_s),
            idle_before_down_s=_int(values, "idle_before_down_s", base.idle_before_down_s),
            step_up=_int(values, "step_up", base.step_up),
            step_down=_int(values, "step_down", base.step_down),
            webhook_url=url if isinstance(url, str) and url else None,
        )
    except AutoscaleValueError:
        return base


@dataclass(frozen=True)
class ScaleRequest:
    desired: int
    current: int
    reason: str
    metrics: QueueMetrics
    at: datetime


class OrchestratorError(Exception):
    """Оркестратор не принял решение (сеть, код ответа, код выхода команды)."""


class IQueueMetricsReader(Protocol):
    async def read(self, now: datetime) -> QueueMetrics: ...


class IRunnerOrchestrator(Protocol):
    """Исполнитель решения: привести число раннеров к `desired`. Бросает `OrchestratorError`."""

    async def scale_to(self, request: ScaleRequest) -> None: ...

    async def current(self) -> int | None:
        """Сколько раннеров считает у себя оркестратор; `None`, если не умеет сказать."""
        ...
