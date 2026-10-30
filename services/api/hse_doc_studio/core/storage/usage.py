"""Занятое место установки по записям базы: бакет не перечисляется, это дорого и медленно."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from hse_doc_studio.core.listing import Paged, SortOrder, Window

STORAGE_OWNER_SORT_FIELDS = ("projects", "bytes", "name")


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


class StorageOwnerKind(StrEnum):
    user = "user"
    org = "org"


@dataclass(frozen=True)
class StorageOwner:
    """Владелец живых проектов: сколько их и сколько места они занимают по последнему измерению."""

    kind: StorageOwnerKind
    id: str
    name: str
    email: str | None
    projects: int
    bytes: int


@dataclass(frozen=True)
class StorageOwnerQuery:
    q: str | None = None
    kinds: frozenset[StorageOwnerKind] = frozenset()
    sort: SortOrder = SortOrder("projects", descending=True)
    window: Window = Window()


class IStorageUsageReader(Protocol):
    async def read(self, now: datetime) -> StorageUsage: ...

    async def list_owners(self, query: StorageOwnerQuery) -> Paged[StorageOwner]:
        """Люди и организации с живыми проектами; поиск по имени и почте, порядок и окно в хранилище."""
        ...
