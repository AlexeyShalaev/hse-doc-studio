"""Автомат отказов провайдера: после подряд идущих сбоев закрывает его на время, затем пробует одним вызовом.

Состояния: `closed` (пропускает), `open` (отказывает быстро до `open_for_s`), `half_open` (пропускает один
пробный вызов; успех закрывает, сбой открывает снова). Часы приходят аргументом, ввода-вывода нет.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import UUID


class BreakerState(StrEnum):
    closed = "closed"
    open = "open"
    half_open = "half_open"


@dataclass
class _Entry:
    failures: int = 0
    opened_at: float | None = None
    probing: bool = False


@dataclass
class CircuitBreakers:
    threshold: int = 5
    open_for_s: float = 30.0
    _entries: dict[UUID, _Entry] = field(default_factory=dict)

    def state(self, provider_id: UUID, now: float) -> BreakerState:
        entry = self._entries.get(provider_id)
        if entry is None or entry.opened_at is None:
            return BreakerState.closed
        if now - entry.opened_at < self.open_for_s:
            return BreakerState.open
        return BreakerState.half_open

    def allow(self, provider_id: UUID, now: float) -> bool:
        """Можно ли слать вызов. В полуоткрытом состоянии пропускается один пробный."""
        state = self.state(provider_id, now)
        if state is BreakerState.closed:
            return True
        if state is BreakerState.open:
            return False
        entry = self._entries[provider_id]
        if entry.probing:
            return False
        entry.probing = True
        return True

    def allow_peek(self, provider_id: UUID, now: float) -> bool:
        """То же, что `allow`, но без занятия пробного вызова: для упорядочения замен."""
        state = self.state(provider_id, now)
        if state is BreakerState.closed:
            return True
        entry = self._entries.get(provider_id)
        return state is BreakerState.half_open and entry is not None and not entry.probing

    def success(self, provider_id: UUID) -> None:
        self._entries.pop(provider_id, None)

    def failure(self, provider_id: UUID, now: float) -> None:
        entry = self._entries.setdefault(provider_id, _Entry())
        entry.failures += 1
        entry.probing = False
        if entry.failures >= self.threshold or entry.opened_at is not None:
            entry.opened_at = now

    def release_probe(self, provider_id: UUID) -> None:
        """Пробный вызов закончился ни успехом, ни сбоем провайдера (отмена): слот пробы освобождается."""
        entry = self._entries.get(provider_id)
        if entry is not None:
            entry.probing = False

    def failures(self, provider_id: UUID) -> int:
        entry = self._entries.get(provider_id)
        return entry.failures if entry is not None else 0
