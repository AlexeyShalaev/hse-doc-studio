"""Политика автомасштабирования: границы, рост по глубине и ожиданию, остывание, окно простоя, уменьшение."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from hse_doc_studio.core.jobs.autoscale import (
    AutoscaleMode,
    AutoscalePolicy,
    AutoscaleState,
    AutoscaleValueError,
    QueueMetrics,
    ScaleAction,
    ScaleReason,
    decide,
    policy_from,
    policy_to_settings,
)

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
POLICY = AutoscalePolicy(
    mode=AutoscaleMode.compose,
    min_runners=1,
    max_runners=5,
    target_queue_per_slot=2.0,
    scale_up_wait_s=30,
    cooldown_up_s=60,
    cooldown_down_s=300,
    idle_before_down_s=120,
    step_up=2,
    step_down=1,
)


def _metrics(
    *, queued: int = 0, wait: float = 0, running: int = 0, runners: int = 2, per_runner: int = 2
) -> QueueMetrics:
    return QueueMetrics(queued, wait, running, runners, runners * per_runner)


def test__decide__below_minimum_grows_to_minimum_ignoring_cooldown() -> None:
    state = AutoscaleState(last_up_at=NOW)

    decision, _ = decide(POLICY, _metrics(runners=0), state, NOW)

    assert (decision.action, decision.desired, decision.reason) == (ScaleAction.up, 1, ScaleReason.below_min)


def test__decide__above_maximum_shrinks_to_maximum() -> None:
    decision, _ = decide(POLICY, _metrics(runners=8), AutoscaleState(), NOW)

    assert (decision.action, decision.desired, decision.reason) == (ScaleAction.down, 5, ScaleReason.above_max)


def test__decide__deep_queue_grows_by_step() -> None:
    decision, _ = decide(POLICY, _metrics(queued=20, running=4), AutoscaleState(), NOW)

    assert (decision.action, decision.desired, decision.reason) == (ScaleAction.up, 4, ScaleReason.queue_depth)


def test__decide__old_waiting_job_grows_even_when_queue_is_short() -> None:
    decision, _ = decide(POLICY, _metrics(queued=1, wait=45, running=4), AutoscaleState(), NOW)

    assert (decision.action, decision.reason) == (ScaleAction.up, ScaleReason.queue_wait)
    assert decision.desired == 3


def test__decide__short_fresh_queue_is_left_alone() -> None:
    decision, _ = decide(POLICY, _metrics(queued=2, wait=3, running=4), AutoscaleState(), NOW)

    assert (decision.action, decision.reason) == (ScaleAction.hold, ScaleReason.balanced)


def test__decide__growth_never_exceeds_what_the_jobs_can_use() -> None:
    decision, _ = decide(POLICY, _metrics(queued=5, wait=99, running=0, runners=1, per_runner=4), AutoscaleState(), NOW)

    assert decision.desired == 2


def test__decide__growth_is_capped_by_the_ceiling() -> None:
    decision, _ = decide(POLICY, _metrics(queued=100, running=8, runners=4), AutoscaleState(), NOW)

    assert decision.desired == 5


def test__decide__at_ceiling_holds_with_reason() -> None:
    decision, _ = decide(POLICY, _metrics(queued=100, running=10, runners=5), AutoscaleState(), NOW)

    assert (decision.action, decision.reason) == (ScaleAction.hold, ScaleReason.at_max)


def test__decide__growth_waits_out_the_up_cooldown_and_reports_remaining_seconds() -> None:
    state = AutoscaleState(last_up_at=NOW - timedelta(seconds=40))

    decision, _ = decide(POLICY, _metrics(queued=20, running=4), state, NOW)

    assert (decision.action, decision.reason, decision.wait_s) == (ScaleAction.hold, ScaleReason.cooldown_up, 20)


def test__decide__no_runners_and_waiting_jobs_asks_for_one_even_with_zero_minimum() -> None:
    zero = AutoscalePolicy(mode=AutoscaleMode.compose, min_runners=0, max_runners=3)

    decision, _ = decide(zero, QueueMetrics(queued=1, runners_online=0), AutoscaleState(), NOW)

    assert (decision.action, decision.desired) == (ScaleAction.up, 1)


def test__decide__idle_starts_the_window_and_waits_for_it() -> None:
    first, state = decide(POLICY, _metrics(runners=3), AutoscaleState(), NOW)
    later, _ = decide(POLICY, _metrics(runners=3), state, NOW + timedelta(seconds=60))

    assert (first.action, first.reason, first.wait_s) == (ScaleAction.hold, ScaleReason.idle_wait, 120)
    assert state.idle_since == NOW
    assert (later.action, later.wait_s) == (ScaleAction.hold, 60)


def test__decide__after_idle_window_shrinks_by_one_step() -> None:
    state = AutoscaleState(idle_since=NOW - timedelta(seconds=130))

    decision, _ = decide(POLICY, _metrics(runners=3), state, NOW)

    assert (decision.action, decision.desired, decision.reason) == (ScaleAction.down, 2, ScaleReason.idle)


def test__decide__shrink_waits_for_the_down_cooldown_after_a_recent_change() -> None:
    state = AutoscaleState(idle_since=NOW - timedelta(seconds=600), last_up_at=NOW - timedelta(seconds=100))

    decision, _ = decide(POLICY, _metrics(runners=3), state, NOW)

    assert (decision.action, decision.reason, decision.wait_s) == (ScaleAction.hold, ScaleReason.cooldown_down, 200)


def test__decide__never_shrinks_below_the_minimum() -> None:
    state = AutoscaleState(idle_since=NOW - timedelta(seconds=999))

    decision, _ = decide(POLICY, _metrics(runners=1), state, NOW)

    assert (decision.action, decision.reason) == (ScaleAction.hold, ScaleReason.at_min)


def test__decide__running_jobs_that_do_not_fit_the_smaller_pool_block_shrinking_and_reset_idle() -> None:
    state = AutoscaleState(idle_since=NOW - timedelta(seconds=999))

    decision, new_state = decide(POLICY, _metrics(runners=3, running=5), state, NOW)

    assert (decision.action, decision.reason) == (ScaleAction.hold, ScaleReason.busy)
    assert new_state.idle_since is None


def test__decide__growth_pressure_resets_the_idle_window() -> None:
    state = AutoscaleState(idle_since=NOW - timedelta(seconds=999))

    _, new_state = decide(POLICY, _metrics(queued=50, running=4), state, NOW)

    assert new_state.idle_since is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"min_runners": -1},
        {"max_runners": 0},
        {"min_runners": 3, "max_runners": 2},
        {"max_runners": 1000},
        {"target_queue_per_slot": 0},
        {"step_up": 0},
        {"cooldown_up_s": -5},
        {"mode": AutoscaleMode.webhook},
    ],
)
def test__policy__rejects_out_of_range_values(kwargs: dict[str, object]) -> None:
    with pytest.raises(AutoscaleValueError):
        AutoscalePolicy(**kwargs)  # type: ignore[arg-type]


def test__policy_settings__roundtrip_and_garbage_falls_back_to_defaults() -> None:
    policy = AutoscalePolicy(
        mode=AutoscaleMode.webhook, webhook_url="https://orch.example/scale", min_runners=2, max_runners=9
    )

    assert policy_from({k: v for k, v in policy_to_settings(policy).items() if v is not None}) == policy
    assert policy_from({"autoscale.max": "many", "autoscale.mode": "explode"}) == AutoscalePolicy()
    assert policy_from({"autoscale.min": 9, "autoscale.max": 3}) == AutoscalePolicy()
