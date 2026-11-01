"""Ограничитель частоты в памяти процесса: скользящее окно по ключу."""

from __future__ import annotations

import math
import time
from collections import deque
from collections.abc import Callable

from hse_doc_studio.core.rate_limit import RateDecision, RateRule

_SWEEP_EVERY = 1024


class InMemoryRateLimiter:
    """Счётчики по реплике: при нескольких репликах лимит умножается на их число (этап 6 заменит хранилище).

    Число ключей ограничено `max_keys`: при переполнении самые давние выбрасываются, память не растёт от
    подбора ключей. Все операции синхронные внутри одного цикла событий, замок не нужен.
    """

    def __init__(self, *, clock: Callable[[], float] = time.monotonic, max_keys: int = 50_000) -> None:
        self._clock = clock
        self._max_keys = max_keys
        self._hits: dict[tuple[str, str], deque[float]] = {}
        self._windows: dict[str, float] = {}
        self._calls = 0

    async def hit(self, rule: RateRule, key: str) -> RateDecision:
        now = self._clock()
        self._windows[rule.name] = rule.window_s
        self._calls += 1
        if self._calls % _SWEEP_EVERY == 0:
            self._sweep(now)
        slot = (rule.name, key)
        window = self._hits.get(slot)
        if window is None:
            if len(self._hits) >= self._max_keys:
                self._evict_oldest()
            window = self._hits[slot] = deque()
        edge = now - rule.window_s
        while window and window[0] <= edge:
            window.popleft()
        if len(window) >= rule.limit:
            wait = window[0] + rule.window_s - now
            return RateDecision(allowed=False, retry_after_s=max(1, math.ceil(wait)))
        window.append(now)
        return RateDecision(allowed=True, remaining=rule.limit - len(window))

    def _sweep(self, now: float) -> None:
        for slot in [s for s, w in self._hits.items() if not w or w[-1] <= now - self._windows.get(s[0], 0)]:
            del self._hits[slot]

    def _evict_oldest(self) -> None:
        oldest = min(self._hits, key=lambda s: self._hits[s][-1] if self._hits[s] else 0.0)
        del self._hits[oldest]
