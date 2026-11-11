"""Подставные источники, статистика, проба места и уведомления для тестов жизненного цикла данных."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.lifecycle.ports import (
    ExpiredCount,
    PurgeContext,
    PurgeResult,
    RunStat,
    SourceSize,
    VolumeUsage,
)
from hse_doc_studio.core.lifecycle.sweeps import LifecycleSweep, SweepStatus, SweepStep, closed_steps


class FakeSource:
    """`expired`: сколько записей «старше срока» отвечает предпросмотр (None: счёт не удался).

    `sizes`: размеры по очереди замеров (последний повторяется), чтобы проверить освобождённое место.
    """

    def __init__(
        self,
        key: str,
        *,
        removed: int = 3,
        fail: bool = False,
        expired: int | None = 5,
        sizes: Sequence[int] = (1024,),
    ) -> None:
        self.key = key
        self.removed = removed
        self.fail = fail
        self.expired = expired
        self.sizes = list(sizes)
        self.seen: list[PurgeContext] = []
        self.counted: list[tuple[datetime | None, int]] = []
        self.gate: asyncio.Event | None = None

    async def measure(self) -> SourceSize:
        size = self.sizes.pop(0) if len(self.sizes) > 1 else self.sizes[0]
        return SourceSize(bytes=size, rows=7)

    async def purge(self, ctx: PurgeContext) -> PurgeResult:
        self.seen.append(ctx)
        if self.gate is not None:
            await self.gate.wait()
        if self.fail:
            raise RuntimeError("boom")
        return PurgeResult(removed=self.removed, partitions_dropped=1)

    async def count_expired(self, now: datetime, cutoff: datetime | None, cap: int) -> ExpiredCount:
        self.counted.append((cutoff, cap))
        if self.expired is None:
            return ExpiredCount(None, cutoff)
        return ExpiredCount(min(self.expired, cap + 1), cutoff)


class InMemoryLifecycleSweeps:
    """Те же правила, что у Postgres: один идущий прогон, 20 последних, закрытый прогон не меняется."""

    def __init__(self) -> None:
        self.rows: dict[str, LifecycleSweep] = {}

    async def create(self, sweep: LifecycleSweep, *, keep: int) -> bool:
        if any(s.status.active for s in self.rows.values()):
            return False
        self.rows[sweep.id] = sweep
        recent = sorted(self.rows.values(), key=lambda s: s.started_at, reverse=True)[:keep]
        keep_ids = {s.id for s in recent}
        self.rows = {k: v for k, v in self.rows.items() if k in keep_ids or v.status.active}
        return True

    async def get(self, sweep_id: str) -> LifecycleSweep | None:
        return self.rows.get(sweep_id)

    async def latest(self) -> LifecycleSweep | None:
        if not self.rows:
            return None
        return max(self.rows.values(), key=lambda s: (s.status.active, s.started_at))

    async def save_steps(self, sweep_id: str, steps: Sequence[SweepStep], *, at: datetime) -> SweepStatus | None:
        sweep = self.rows.get(sweep_id)
        if sweep is None:
            return None
        if sweep.status.active:
            self.rows[sweep_id] = replace(sweep, steps=tuple(steps), updated_at=at)
        return sweep.status

    async def request_cancel(self, sweep_id: str, *, at: datetime) -> LifecycleSweep | None:
        sweep = self.rows.get(sweep_id)
        if sweep is not None and sweep.status is SweepStatus.running:
            sweep = self.rows[sweep_id] = replace(sweep, status=SweepStatus.cancelling)
        return sweep

    async def finish(
        self, sweep_id: str, status: SweepStatus, steps: Sequence[SweepStep], *, at: datetime
    ) -> LifecycleSweep | None:
        sweep = self.rows.get(sweep_id)
        if sweep is None or not sweep.status.active:
            return None
        done = replace(sweep, status=status, steps=tuple(steps), updated_at=at, finished_at=at)
        self.rows[sweep_id] = done
        return done

    async def interrupt_stale(self, *, before: datetime, at: datetime) -> list[LifecycleSweep]:
        closed: list[LifecycleSweep] = []
        for key, sweep in list(self.rows.items()):
            if sweep.status.active and sweep.updated_at < before:
                done = replace(
                    sweep,
                    status=SweepStatus.interrupted,
                    steps=closed_steps(sweep.steps),
                    updated_at=at,
                    finished_at=at,
                )
                self.rows[key] = done
                closed.append(done)
        return closed


class FakeRuns:
    def __init__(self) -> None:
        self.rows: dict[str, RunStat] = {}

    async def record(self, key: str, *, at: datetime, duration_ms: int, removed: int, error: str | None) -> None:
        old = self.rows.get(key)
        self.rows[key] = RunStat(
            key,
            at,
            duration_ms,
            removed,
            error,
            (old.runs if old else 0) + 1,
            (old.total_removed if old else 0) + removed,
        )

    async def all(self) -> dict[str, RunStat]:
        return dict(self.rows)


class FakeProbe:
    def __init__(self, ratio: float) -> None:
        self.ratio = ratio

    async def volumes(self) -> list[VolumeUsage]:
        total = 1000
        return [
            VolumeUsage("data", int(total * self.ratio), total, int(total * (1 - self.ratio))),
            VolumeUsage("database", 5, None, None),
        ]

    async def database_bytes(self) -> int:
        return 5


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, NotificationKind, NotificationPayload, str | None]] = []

    async def notify(
        self,
        user_id: str,
        kind: NotificationKind,
        payload: NotificationPayload,
        *,
        dedupe_key: str | None = None,
        mail: bool = True,
    ) -> None:
        self.sent.append((user_id, kind, payload, dedupe_key))


class FakeAdmins:
    async def active_admin_ids(self) -> list[str]:
        return ["a1", "a2"]
