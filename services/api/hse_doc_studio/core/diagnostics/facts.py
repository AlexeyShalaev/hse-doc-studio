"""Факты, которые снимают пробы инфраструктуры; вердикт по ним выносят чистые правила (`rules.py`)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from hse_doc_studio.core.lifecycle.disk import StorageLevel


@dataclass(frozen=True)
class DbFacts:
    latency_ms: float | None = None
    version: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class MigrationFacts:
    current: str | None
    head: str
    known: bool = True  # текущая ревизия базы есть в цепочке этого образа


@dataclass(frozen=True)
class ObjectFacts:
    kind: str  # s3 | fs
    bucket: str | None = None
    roundtrip_ms: float | None = None
    error_stage: str | None = None  # check | write | read | mismatch | delete


@dataclass(frozen=True)
class RunnerFacts:
    registered: int = 0
    online: int = 0
    queued: int = 0


@dataclass(frozen=True)
class JobFacts:
    queued: int = 0
    oldest_wait_s: float = 0.0
    stuck: int = 0
    oldest_overdue_s: float = 0.0


@dataclass(frozen=True)
class DiskFacts:
    level: StorageLevel = StorageLevel.ok
    volume: str | None = None
    percent: int | None = None
    safe_mode: bool = False
    biggest_source: str | None = None
    lifecycle_errors: int = 0


@dataclass(frozen=True)
class TlsFacts:
    configured: bool
    https: bool = True
    host: str | None = None
    days_left: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class BackupFacts:
    enabled: bool
    has_destination: bool
    last_ok_at: datetime | None = None
    last_failed: bool = False
    now: datetime | None = None


@dataclass(frozen=True)
class SmtpFacts:
    configured: bool
    latency_ms: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class TaskFact:
    name: str
    interval_s: float
    runs: int
    failures: int
    last_run_at: datetime | None


@dataclass(frozen=True)
class SchedulerFacts:
    leader_present: bool
    leader_here: bool
    tasks: list[TaskFact] = field(default_factory=list)
    last_tick_at: datetime | None = None
    tick_interval_s: float = 300.0
    now: datetime | None = None
