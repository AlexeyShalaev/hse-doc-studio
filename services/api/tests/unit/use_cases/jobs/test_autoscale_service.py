"""Цикл автомасштабирования: исполнение решения оркестратором, остывание в настройках, отказ оркестратора, режим off."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hse_doc_studio.api.observability.autoscale_metrics import autoscale_collector
from hse_doc_studio.core.jobs.autoscale import (
    AutoscaleMode,
    AutoscalePolicy,
    OrchestratorError,
    QueueMetrics,
    ScaleAction,
    ScaleRequest,
    policy_to_settings,
)
from hse_doc_studio.use_cases.jobs.autoscale import KEY_LAST_UP, AutoscaleService

from tests.fakes.auth import InMemoryAuditLog
from tests.fakes.identity import InMemoryInstanceSettingsRepository

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
BUSY = QueueMetrics(queued=30, oldest_wait_s=50, running=4, runners_online=2, slots_total=4)


class Metrics:
    def __init__(self, value: QueueMetrics) -> None:
        self.value = value

    async def read(self, now: datetime) -> QueueMetrics:
        return self.value


class Orchestrator:
    def __init__(self, error: Exception | None = None) -> None:
        self.requests: list[ScaleRequest] = []
        self.error = error

    async def scale_to(self, request: ScaleRequest) -> None:
        if self.error is not None:
            raise self.error
        self.requests.append(request)

    async def current(self) -> int | None:
        return 7


class Factory:
    def __init__(self, orchestrator: Orchestrator | None) -> None:
        self.orchestrator = orchestrator

    def create(self, policy: AutoscalePolicy) -> Orchestrator | None:
        return self.orchestrator


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


async def _rig(
    mode: AutoscaleMode = AutoscaleMode.compose, error: Exception | None = None, metrics: QueueMetrics = BUSY
):
    repo = InMemoryInstanceSettingsRepository()
    policy = AutoscalePolicy(mode=mode, min_runners=1, max_runners=6, webhook_url=None, cooldown_up_s=60)
    for key, value in policy_to_settings(policy).items():
        if value is not None:
            await repo.set(key, value, source="admin")
    orchestrator = Orchestrator(error)
    audit, clock = InMemoryAuditLog(), Clock()
    service = AutoscaleService(repo, Metrics(metrics), Factory(orchestrator), audit, clock=clock)  # type: ignore[arg-type]
    return service, orchestrator, repo, audit, clock


async def test__tick__growth_is_sent_to_the_orchestrator_recorded_and_audited() -> None:
    service, orchestrator, repo, audit, _ = await _rig()

    decision = await service.tick()

    assert decision.action is ScaleAction.up
    assert [(r.desired, r.current, r.reason) for r in orchestrator.requests] == [(4, 2, "queue_depth")]
    assert (await repo.get_all())[KEY_LAST_UP] == NOW.isoformat()
    assert [e.action for e in await audit.list()] == ["autoscale.scaled"]


async def test__tick__second_tick_inside_the_cooldown_does_not_call_the_orchestrator_again() -> None:
    service, orchestrator, _, _, clock = await _rig()
    await service.tick()

    clock.now = NOW + timedelta(seconds=20)
    held = await service.tick()
    clock.now = NOW + timedelta(seconds=61)
    again = await service.tick()

    assert (held.action, held.wait_s) == (ScaleAction.hold, 40)
    assert again.action is ScaleAction.up
    assert len(orchestrator.requests) == 2


async def test__tick__orchestrator_refusal_is_remembered_and_does_not_start_the_cooldown() -> None:
    service, _, repo, audit, _ = await _rig(error=OrchestratorError("webhook answered 500"))

    await service.tick()
    status = await service.evaluate()

    assert KEY_LAST_UP not in await repo.get_all()
    assert status.last_outcome is not None
    assert (status.last_outcome.ok, status.last_outcome.error) == (False, "webhook answered 500")
    assert await audit.list() == []


async def test__tick__mode_off_computes_the_decision_but_never_calls_anything() -> None:
    service, orchestrator, repo, _, _ = await _rig(mode=AutoscaleMode.off)
    service._factory = Factory(orchestrator)  # type: ignore[assignment]

    decision = await service.tick()

    assert decision.action is ScaleAction.up
    assert orchestrator.requests == []
    assert KEY_LAST_UP not in await repo.get_all()


async def test__evaluate__reports_metrics_decision_and_orchestrator_view() -> None:
    service, *_ = await _rig()

    status = await service.evaluate()

    assert status.metrics == BUSY
    assert status.decision.desired == 4
    assert status.orchestrator_current == 7


async def test__metrics_collector__exposes_queue_and_desired_runners() -> None:
    service, *_ = await _rig()
    collect = autoscale_collector(lambda: service.last_seen)
    assert list(collect()) == []

    await service.tick()
    text = "\n".join(collect())

    assert "hse_runner_queue_depth 30" in text
    assert "hse_runners_online 2" in text
    assert "hse_autoscale_desired_runners 4" in text
