"""Общий пул реплик интерактивного сервиса: наименее занятая реплика, доля на пользователя, размыкание цепи.

Пул не знает, что за сервис за репликами: вызывающий передаёт функцию, которая получает URL реплики.
Всё синхронно внутри одного цикла событий (замки не нужны), время берётся из `clock` для тестов.
"""

from __future__ import annotations

import math
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

import structlog

from hse_doc_studio.core.service_pool import ServiceBusyError, ServiceUnavailableError

logger = structlog.get_logger()

T = TypeVar("T")


@dataclass(frozen=True)
class PoolLimits:
    max_inflight_per_replica: int = 4
    # Долю пользователя пополняют `user_rate_per_s` в секунду до `user_burst` запросов в запасе.
    user_rate_per_s: float = 2.0
    user_burst: int = 20
    # Столько подряд неудач реплики размыкают цепь на `circuit_open_s`; потом пробный запрос.
    circuit_failures: int = 3
    circuit_open_s: float = 30.0
    max_users: int = 10_000


@dataclass
class ReplicaState:
    url: str
    inflight: int = 0
    failures: int = 0
    open_until: float = 0.0
    trial: bool = False
    healthy: bool = True


@dataclass(frozen=True)
class ReplicaSnapshot:
    url: str
    inflight: int
    circuit_open: bool
    healthy: bool


class _Bucket:
    __slots__ = ("stamp", "tokens")

    def __init__(self, tokens: float, stamp: float) -> None:
        self.tokens = tokens
        self.stamp = stamp


class ServicePool:
    def __init__(
        self,
        name: str,
        replicas: Sequence[str],
        limits: PoolLimits | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self._limits = limits or PoolLimits()
        self._clock = clock
        self._replicas = [ReplicaState(url.rstrip("/")) for url in dict.fromkeys(replicas)]
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    @property
    def configured(self) -> bool:
        return bool(self._replicas)

    def snapshot(self) -> list[ReplicaSnapshot]:
        now = self._clock()
        return [ReplicaSnapshot(r.url, r.inflight, r.open_until > now, r.healthy) for r in self._replicas]

    def _take_token(self, user_key: str) -> None:
        limits = self._limits
        now = self._clock()
        bucket = self._buckets.get(user_key)
        if bucket is None:
            if len(self._buckets) >= limits.max_users:
                self._buckets.popitem(last=False)
            bucket = self._buckets[user_key] = _Bucket(float(limits.user_burst), now)
        else:
            self._buckets.move_to_end(user_key)
            bucket.tokens = min(float(limits.user_burst), bucket.tokens + (now - bucket.stamp) * limits.user_rate_per_s)
            bucket.stamp = now
        if bucket.tokens < 1.0:
            wait = (1.0 - bucket.tokens) / limits.user_rate_per_s
            raise ServiceBusyError(f"{self.name}: user rate limit", math.ceil(wait))
        bucket.tokens -= 1.0

    def _pick(self) -> ReplicaState:
        now = self._clock()
        limits = self._limits
        candidates: list[ReplicaState] = []
        soonest: float | None = None
        saturated = False
        for replica in self._replicas:
            if not replica.healthy:
                continue
            if replica.open_until > now or (replica.failures >= limits.circuit_failures and replica.trial):
                remaining = max(replica.open_until - now, 1.0)
                soonest = remaining if soonest is None else min(soonest, remaining)
                continue
            if replica.inflight >= limits.max_inflight_per_replica:
                saturated = True
                continue
            candidates.append(replica)
        if not candidates:
            if saturated:
                raise ServiceBusyError(f"{self.name}: all replicas busy", 1)
            raise ServiceUnavailableError(f"{self.name}: no healthy replica", math.ceil(soonest or 5))
        return min(candidates, key=lambda r: r.inflight)

    def pick_url(self) -> str:
        """URL наименее занятой здоровой реплики без учёта доли пользователя (проверки внутри процесса)."""
        return self._pick().url

    async def call(
        self,
        user_key: str,
        fn: Callable[[str], Awaitable[T]],
        *,
        is_fault: Callable[[BaseException], bool] = lambda _exc: True,
    ) -> T:
        """Вызвать `fn(url)` на наименее занятой реплике. `is_fault` решает, считать ли ошибку отказом реплики."""
        self._take_token(user_key)
        replica = self._pick()
        half_open = replica.failures >= self._limits.circuit_failures
        if half_open:
            replica.trial = True
        replica.inflight += 1
        try:
            result = await fn(replica.url)
        except BaseException as exc:
            if is_fault(exc):
                self._failed(replica)
            elif half_open:
                replica.trial = False
            raise
        else:
            replica.failures = 0
            replica.trial = False
            return result
        finally:
            replica.inflight -= 1

    def _failed(self, replica: ReplicaState) -> None:
        replica.failures += 1
        replica.trial = False
        if replica.failures >= self._limits.circuit_failures:
            replica.open_until = self._clock() + self._limits.circuit_open_s
            logger.warning("service_pool.circuit_open", pool=self.name, replica=replica.url, failures=replica.failures)

    async def probe(self, check: Callable[[str], Awaitable[bool]]) -> list[ReplicaSnapshot]:
        """Опросить каждую реплику: здоровая сбрасывает цепь, нездоровая выпадает из выбора до следующего опроса."""
        for replica in self._replicas:
            try:
                ok = await check(replica.url)
            except Exception:  # noqa: BLE001 — любая ошибка опроса означает нездоровую реплику
                ok = False
            replica.healthy = ok
            if ok:
                replica.failures = 0
                replica.open_until = 0.0
                replica.trial = False
        return self.snapshot()
