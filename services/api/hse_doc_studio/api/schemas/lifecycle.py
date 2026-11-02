"""Схемы админки «Хранение данных»: источники роста, сроки хранения, тома и пороги."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from hse_doc_studio.api.schemas.common import StrictModel

GroupName = Literal["database", "objects", "disk", "logs"]
StrategyName = Literal["partition_drop", "delete_batches", "file_sweep", "own_task", "on_write", "infra"]
DaysSource = Literal["admin", "env", "default", "fixed"]
LevelName = Literal["ok", "warning", "critical"]


class LifecycleLastRun(StrictModel):
    at: datetime | None
    duration_ms: int | None
    removed: int | None
    error: str | None
    runs: int
    total_removed: int | None


class LifecycleSource(StrictModel):
    key: str
    group: GroupName
    strategy: StrategyName
    growth: Literal["low", "medium", "high"]
    # Срок хранения в днях; null: без срока (окружение выключило очистку) либо срок не задаётся числом дней.
    days: int | None
    days_source: DaysSource
    min_days: int | None
    max_days: int | None
    default_days: int | None
    editable: bool
    run_now: bool
    protected: bool
    env: str | None
    bytes: int | None
    rows: int | None
    partitions: int | None
    last_run: LifecycleLastRun | None


class LifecycleVolume(StrictModel):
    name: str
    used_bytes: int
    total_bytes: int | None
    free_bytes: int | None
    used_ratio: float | None
    level: LevelName


class StorageThresholdsBody(StrictModel):
    warn_percent: int = Field(ge=50, le=95)
    critical_percent: int = Field(ge=60, le=99)


class LifecycleOverviewBody(StrictModel):
    sources: list[LifecycleSource]
    volumes: list[LifecycleVolume]
    thresholds: StorageThresholdsBody
    level: LevelName
    safe_mode: bool


class UpdateRetentionRequest(StrictModel):
    # null снимает правку админа: дальше действует умолчание.
    days: int | None = Field(default=None, ge=1, le=3660)


class LifecycleRunBody(StrictModel):
    key: str
    removed: int
    partitions_dropped: int
    more: bool
    error: str | None
