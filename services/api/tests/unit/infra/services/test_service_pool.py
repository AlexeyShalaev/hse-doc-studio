from __future__ import annotations

import pytest
from hse_doc_studio.core.service_pool import ServiceBusyError, ServiceUnavailableError
from hse_doc_studio.infra.services.pool import PoolLimits, ServicePool


class _Clock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def _pool(clock: _Clock, replicas: tuple[str, ...] = ("http://a", "http://b"), **limits: float) -> ServicePool:
    return ServicePool("lt", replicas, PoolLimits(**limits), clock=clock)  # type: ignore[arg-type]


async def _ok(url: str) -> str:
    return url


async def _boom(_url: str) -> str:
    raise ConnectionError("down")


@pytest.mark.unit
async def test__pool__picks_least_inflight_replica() -> None:
    import asyncio

    clock = _Clock()
    pool = _pool(clock)
    gate = asyncio.Event()

    async def slow(url: str) -> str:
        await gate.wait()
        return url

    first = asyncio.create_task(pool.call("u1", slow))
    await asyncio.sleep(0)
    second = await pool.call("u2", _ok)
    gate.set()
    assert await first == "http://a"
    assert second == "http://b"


@pytest.mark.unit
async def test__pool__user_bucket_refills_and_returns_retry_after() -> None:
    clock = _Clock()
    pool = _pool(clock, user_burst=2, user_rate_per_s=0.5)
    await pool.call("u", _ok)
    await pool.call("u", _ok)
    with pytest.raises(ServiceBusyError) as err:
        await pool.call("u", _ok)
    assert err.value.retry_after_s == 2
    await pool.call("other", _ok)
    clock.now += 2
    await pool.call("u", _ok)


@pytest.mark.unit
async def test__pool__saturated_replicas_are_busy() -> None:
    import asyncio

    clock = _Clock()
    pool = _pool(clock, ("http://a",), max_inflight_per_replica=1)
    gate = asyncio.Event()

    async def slow(url: str) -> str:
        await gate.wait()
        return url

    task = asyncio.create_task(pool.call("u1", slow))
    await asyncio.sleep(0)
    with pytest.raises(ServiceBusyError):
        await pool.call("u2", _ok)
    gate.set()
    await task


@pytest.mark.unit
async def test__pool__circuit_opens_then_half_open_recovers() -> None:
    clock = _Clock()
    pool = _pool(clock, ("http://a",), circuit_failures=2, circuit_open_s=10)
    for _ in range(2):
        with pytest.raises(ConnectionError):
            await pool.call("u", _boom)
    with pytest.raises(ServiceUnavailableError) as err:
        await pool.call("u", _ok)
    assert err.value.retry_after_s == 10
    clock.now += 11
    assert await pool.call("u", _ok) == "http://a"
    assert not pool.snapshot()[0].circuit_open


@pytest.mark.unit
async def test__pool__not_a_fault_does_not_trip_circuit() -> None:
    clock = _Clock()
    pool = _pool(clock, ("http://a",), circuit_failures=1)
    with pytest.raises(ValueError, match="400"):
        await pool.call("u", _bad_request, is_fault=lambda _e: False)
    assert await pool.call("u", _ok) == "http://a"


async def _bad_request(_url: str) -> str:
    raise ValueError("400")


@pytest.mark.unit
async def test__pool__probe_removes_unhealthy_and_returns_when_back() -> None:
    clock = _Clock()
    pool = _pool(clock)
    alive = {"http://a": False, "http://b": True}

    async def check(url: str) -> bool:
        return alive[url]

    await pool.probe(check)
    assert await pool.call("u", _ok) == "http://b"
    alive["http://a"] = True
    await pool.probe(check)
    assert all(r.healthy for r in pool.snapshot())


@pytest.mark.unit
async def test__pool__without_replicas_is_unavailable() -> None:
    pool = _pool(_Clock(), ())
    assert not pool.configured
    with pytest.raises(ServiceUnavailableError):
        await pool.call("u", _ok)
