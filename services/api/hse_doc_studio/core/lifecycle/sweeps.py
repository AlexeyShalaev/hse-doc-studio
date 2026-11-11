"""Прогон «Освободить место»: все ручные источники движка подряд на сервере (storage-cleanup.md, 5.4).

Прогон живёт строкой в Postgres, а не в памяти api: запрос хода и остановка могут прийти на другую реплику.
Одновременно идёт не больше одного прогона (частичный уникальный индекс), строка без обновления дольше
`STALE_AFTER` считается прерванной: реплика, которая его вела, перезапустилась.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

# Сколько последних прогонов хранить (стратегия on_write в реестре): остальные завершённые стираются при вставке.
KEEP_SWEEPS = 20
# Шаг укладывается в бюджет источника (120 с) с замерами до и после, поэтому 5 минут без обновления это обрыв.
STALE_AFTER = timedelta(minutes=5)
# Потолок счёта в предпросмотре: дальше «больше 100 000 записей».
PREVIEW_CAP = 100_000
STEP_ERROR_MAX = 300


class SweepStatus(StrEnum):
    running = "running"
    cancelling = "cancelling"
    done = "done"
    cancelled = "cancelled"
    error = "error"
    interrupted = "interrupted"

    @property
    def active(self) -> bool:
        return self in _ACTIVE


_ACTIVE = frozenset({SweepStatus.running, SweepStatus.cancelling})
ACTIVE_STATUSES: tuple[str, ...] = tuple(s.value for s in SweepStatus if s.active)


class StepStatus(StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    error = "error"
    skipped = "skipped"


@dataclass(frozen=True)
class SweepStep:
    key: str
    status: StepStatus = StepStatus.pending
    removed: int = 0
    partitions_dropped: int = 0
    # Бюджет источника кончился раньше: остальное уйдёт на плановом тике.
    more: bool = False
    bytes_before: int | None = None
    bytes_after: int | None = None
    error: str | None = None

    @property
    def freed_bytes(self) -> int:
        if self.bytes_before is None or self.bytes_after is None:
            return 0
        return max(0, self.bytes_before - self.bytes_after)


def closed_steps(steps: Sequence[SweepStep]) -> tuple[SweepStep, ...]:
    """Шаги закрытого прогона: оборванный посреди источник это ошибка шага, не начатые пропущены."""
    out: list[SweepStep] = []
    for step in steps:
        if step.status is StepStatus.running:
            out.append(replace(step, status=StepStatus.error, error=step.error or "interrupted"))
        elif step.status is StepStatus.pending:
            out.append(replace(step, status=StepStatus.skipped))
        else:
            out.append(step)
    return tuple(out)


@dataclass(frozen=True)
class LifecycleSweep:
    id: str
    status: SweepStatus
    started_by: str | None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    steps: tuple[SweepStep, ...]

    @property
    def removed_total(self) -> int:
        return sum(s.removed for s in self.steps)

    @property
    def freed_bytes(self) -> int:
        """Освобождено на диске: сумма уменьшений размера источников (DELETE места на диске не отдаёт, S11)."""
        return sum(s.freed_bytes for s in self.steps)

    @property
    def errors(self) -> int:
        return sum(1 for s in self.steps if s.status is StepStatus.error)

    def stale(self, now: datetime) -> bool:
        return self.status.active and now - self.updated_at > STALE_AFTER


class ExcludedReason(StrEnum):
    """Почему источник реестра не входит в «Освободить место» (S12)."""

    protected = "protected"  # журнал аудита вручную не чистится
    own_task = "own_task"  # своя фоновая задача со своим расписанием и замком
    on_write = "on_write"  # предел держится при записи, чистить по сроку нечего
    infra = "infra"  # ограничено инфраструктурой


@dataclass(frozen=True)
class PreviewSource:
    key: str
    days: int | None
    cutoff: datetime | None
    count: int | None
    capped: bool
    bytes: int | None


@dataclass(frozen=True)
class SweepPreview:
    sources: tuple[PreviewSource, ...]
    excluded: tuple[tuple[str, ExcludedReason], ...]

    @property
    def nothing(self) -> bool:
        return all(s.count == 0 for s in self.sources)


class ILifecycleSweeps(Protocol):
    async def create(self, sweep: LifecycleSweep, *, keep: int) -> bool:
        """Новый прогон; False, если уже идёт другой. Завершённые сверх `keep` последних стираются."""
        ...

    async def get(self, sweep_id: str) -> LifecycleSweep | None: ...

    async def latest(self) -> LifecycleSweep | None:
        """Идущий прогон, иначе последний по времени запуска."""
        ...

    async def save_steps(self, sweep_id: str, steps: Sequence[SweepStep], *, at: datetime) -> SweepStatus | None:
        """Ход прогона; возвращает текущий статус строки (так ведущая реплика узнаёт об остановке)."""
        ...

    async def request_cancel(self, sweep_id: str, *, at: datetime) -> LifecycleSweep | None:
        """`running` становится `cancelling`; остальные статусы не меняются. None: прогона нет."""
        ...

    async def finish(
        self, sweep_id: str, status: SweepStatus, steps: Sequence[SweepStep], *, at: datetime
    ) -> LifecycleSweep | None:
        """Итог, только если прогон ещё не закрыт (иначе None: его уже закрыли как прерванный)."""
        ...

    async def interrupt_stale(self, *, before: datetime, at: datetime) -> list[LifecycleSweep]:
        """Незавершённые прогоны без обновления с `before` становятся `interrupted`; возвращает закрытые."""
        ...
