"""Автомат отказов: закрывается после серии сбоев, пробует одним вызовом, закрывается обратно при успехе."""

from __future__ import annotations

from uuid import uuid4

from hse_doc_studio.core.ai_gateway.breaker import BreakerState, CircuitBreakers


def test__breaker__opens_after_threshold_and_rejects_until_the_window_passes() -> None:
    breakers, pid = CircuitBreakers(threshold=3, open_for_s=30), uuid4()

    for _ in range(2):
        breakers.failure(pid, 0.0)
    assert breakers.allow(pid, 1.0) is True

    breakers.failure(pid, 1.0)

    assert breakers.state(pid, 2.0) is BreakerState.open
    assert breakers.allow(pid, 2.0) is False
    assert breakers.state(pid, 31.1) is BreakerState.half_open


def test__breaker__half_open_lets_exactly_one_probe_through() -> None:
    breakers, pid = CircuitBreakers(threshold=1, open_for_s=10), uuid4()
    breakers.failure(pid, 0.0)

    assert breakers.allow(pid, 11.0) is True
    assert breakers.allow(pid, 11.0) is False
    breakers.release_probe(pid)
    assert breakers.allow(pid, 11.0) is True


def test__breaker__probe_success_closes_probe_failure_reopens() -> None:
    breakers, a, b = CircuitBreakers(threshold=1, open_for_s=10), uuid4(), uuid4()
    breakers.failure(a, 0.0)
    breakers.failure(b, 0.0)
    assert breakers.allow(a, 11.0)
    assert breakers.allow(b, 11.0)

    breakers.success(a)
    breakers.failure(b, 11.0)

    assert breakers.state(a, 12.0) is BreakerState.closed
    assert breakers.state(b, 12.0) is BreakerState.open
    assert breakers.allow_peek(a, 12.0) is True
    assert breakers.allow_peek(b, 12.0) is False


def test__breaker__success_resets_the_failure_streak() -> None:
    breakers, pid = CircuitBreakers(threshold=3), uuid4()
    breakers.failure(pid, 0.0)
    breakers.failure(pid, 0.0)

    breakers.success(pid)
    breakers.failure(pid, 1.0)

    assert breakers.state(pid, 2.0) is BreakerState.closed
    assert breakers.failures(pid) == 1
