"""Порты жизненного цикла данных: источник роста, статистика прогонов, проба тома."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class SourceSize:
    """Сколько занимает источник сейчас. `rows`: оценка по статистике Postgres (None для файлов)."""

    bytes: int = 0
    rows: int | None = None
    partitions: int | None = None


@dataclass(frozen=True)
class PurgeContext:
    """Условия одного прогона очистки источника.

    `cutoff`: всё, что старше, подлежит удалению (None: срок хранения выключен окружением).
    `deadline`: монотонное время (time.monotonic), после которого прогон пачки не начинают.
    """

    now: datetime
    cutoff: datetime | None
    batch_size: int
    deadline: float


@dataclass(frozen=True)
class PurgeResult:
    removed: int = 0
    partitions_dropped: int = 0
    # Остались ещё записи к удалению: прогон упёрся в бюджет времени и продолжит на следующем тике.
    more: bool = False


class ILifecycleSource(Protocol):
    key: str

    async def measure(self) -> SourceSize: ...

    async def purge(self, ctx: PurgeContext) -> PurgeResult: ...


@dataclass(frozen=True)
class RunStat:
    key: str
    last_run_at: datetime
    last_duration_ms: int
    last_removed: int
    last_error: str | None
    runs: int
    total_removed: int


class ILifecycleRuns(Protocol):
    async def record(self, key: str, *, at: datetime, duration_ms: int, removed: int, error: str | None) -> None: ...

    async def all(self) -> dict[str, RunStat]: ...


@dataclass(frozen=True)
class VolumeUsage:
    """Занятость тома или базы. `used_ratio` None, если ёмкость неизвестна (например, размер базы без лимита)."""

    name: str
    used_bytes: int
    total_bytes: int | None
    free_bytes: int | None = None
    extra: dict[str, int] = field(default_factory=dict)

    @property
    def used_ratio(self) -> float | None:
        if self.total_bytes is None or self.total_bytes <= 0:
            return None
        return (
            1 - (self.free_bytes / self.total_bytes)
            if self.free_bytes is not None
            else self.used_bytes / self.total_bytes
        )


class IStorageProbe(Protocol):
    """Замеры места: том данных, том проектов и размер базы Postgres."""

    async def volumes(self) -> list[VolumeUsage]: ...

    async def database_bytes(self) -> int: ...


class IAdminDirectory(Protocol):
    async def active_admin_ids(self) -> list[str]:
        """Действующие админы установки: кому уходят системные предупреждения."""
        ...
