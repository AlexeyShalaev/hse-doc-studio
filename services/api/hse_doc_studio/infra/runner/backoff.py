from __future__ import annotations

import random
from collections.abc import Callable


class Backoff:
    """Экспоненциальная пауза с разбросом: `next()` растит её, `reset()` сбрасывает после успеха."""

    def __init__(
        self,
        base_s: float = 0.5,
        cap_s: float = 30.0,
        factor: float = 2.0,
        jitter: float = 0.2,
        rng: Callable[[], float] = random.random,
    ) -> None:
        if base_s <= 0 or cap_s < base_s or factor < 1 or not 0 <= jitter < 1:
            raise ValueError("invalid backoff parameters")
        self._base_s = base_s
        self._cap_s = cap_s
        self._factor = factor
        self._jitter = jitter
        self._rng = rng
        self._failures = 0

    @property
    def failures(self) -> int:
        return self._failures

    def next(self) -> float:
        delay = min(self._cap_s, self._base_s * self._factor**self._failures)
        self._failures += 1
        return delay * (1 + self._jitter * (2 * self._rng() - 1))

    def reset(self) -> None:
        self._failures = 0
