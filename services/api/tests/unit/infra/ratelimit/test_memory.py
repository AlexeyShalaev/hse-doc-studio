from __future__ import annotations

import pytest
from hse_doc_studio.core.rate_limit import RateRule
from hse_doc_studio.infra.ratelimit.memory import InMemoryRateLimiter

RULE = RateRule("t", limit=3, window_s=10)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


async def test__hit__over_limit__denied_with_retry_after(clock: Clock) -> None:
    limiter = InMemoryRateLimiter(clock=clock)
    for left in (2, 1, 0):
        decision = await limiter.hit(RULE, "k")
        assert decision.allowed
        assert decision.remaining == left
    clock.now += 4
    denied = await limiter.hit(RULE, "k")
    assert not denied.allowed
    assert denied.retry_after_s == 6


async def test__hit__window_slides__allows_again(clock: Clock) -> None:
    limiter = InMemoryRateLimiter(clock=clock)
    for _ in range(3):
        await limiter.hit(RULE, "k")
    clock.now += 10
    assert (await limiter.hit(RULE, "k")).allowed


async def test__hit__denied_requests_do_not_extend_block(clock: Clock) -> None:
    limiter = InMemoryRateLimiter(clock=clock)
    for _ in range(3):
        await limiter.hit(RULE, "k")
    for _ in range(50):
        clock.now += 0.1
        assert not (await limiter.hit(RULE, "k")).allowed
    clock.now += 5.1
    assert (await limiter.hit(RULE, "k")).allowed


async def test__hit__keys_and_rules_are_isolated(clock: Clock) -> None:
    limiter = InMemoryRateLimiter(clock=clock)
    for _ in range(3):
        await limiter.hit(RULE, "a")
    assert not (await limiter.hit(RULE, "a")).allowed
    assert (await limiter.hit(RULE, "b")).allowed
    assert (await limiter.hit(RateRule("other", 3, 10), "a")).allowed


async def test__hit__retry_after_is_at_least_one_second(clock: Clock) -> None:
    limiter = InMemoryRateLimiter(clock=clock)
    for _ in range(3):
        await limiter.hit(RULE, "k")
    clock.now += 9.99
    assert (await limiter.hit(RULE, "k")).allowed is False
    assert (await limiter.hit(RULE, "k")).retry_after_s == 1


async def test__hit__key_cap__evicts_oldest(clock: Clock) -> None:
    limiter = InMemoryRateLimiter(clock=clock, max_keys=2)
    for key in ("a", "b", "c"):
        clock.now += 1
        await limiter.hit(RULE, key)
    assert len(limiter._hits) == 2
    assert ("t", "a") not in limiter._hits
