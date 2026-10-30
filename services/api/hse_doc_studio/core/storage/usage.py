"""Занятое место установки по записям базы: бакет не перечисляется, это дорого и медленно."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class OwnerUsage:
    owner_id: str
    owner_name: str
    projects: int


@dataclass(frozen=True)
class StorageUsage:
    blob_count: int
    blob_bytes: int
    projects: int
    deleted_projects: int
    top_owners: tuple[OwnerUsage, ...] = field(default_factory=tuple)
    # Том проектов: None, если путь недоступен.
    volume_total_bytes: int | None = None
    volume_free_bytes: int | None = None
    computed_at: datetime | None = None


class IStorageUsageReader(Protocol):
    async def read(self, now: datetime) -> StorageUsage: ...
