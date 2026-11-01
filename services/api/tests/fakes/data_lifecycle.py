"""Подставные источники, статистика, проба места и уведомления для тестов жизненного цикла данных."""

from __future__ import annotations

from datetime import datetime

from hse_doc_studio.core.invitations.entities import NotificationKind, NotificationPayload
from hse_doc_studio.core.lifecycle.ports import PurgeContext, PurgeResult, RunStat, SourceSize, VolumeUsage


class FakeSource:
    def __init__(self, key: str, *, removed: int = 3, fail: bool = False) -> None:
        self.key = key
        self.removed = removed
        self.fail = fail
        self.seen: list[PurgeContext] = []

    async def measure(self) -> SourceSize:
        return SourceSize(bytes=1024, rows=7)

    async def purge(self, ctx: PurgeContext) -> PurgeResult:
        self.seen.append(ctx)
        if self.fail:
            raise RuntimeError("boom")
        return PurgeResult(removed=self.removed, partitions_dropped=1)


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
        self, user_id: str, kind: NotificationKind, payload: NotificationPayload, *, dedupe_key: str | None = None
    ) -> None:
        self.sent.append((user_id, kind, payload, dedupe_key))


class FakeAdmins:
    async def active_admin_ids(self) -> list[str]:
        return ["a1", "a2"]
