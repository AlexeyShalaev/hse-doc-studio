"""Память вместо счётчиков расхода и таблиц проектов для проверки квот."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID

from hse_doc_studio.core.jobs.quotas import QuotaOwnerKind
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.core.quotas.protocols import CounterTotal, ProjectOwner


class InMemoryUsageCounters:
    def __init__(self) -> None:
        self.rows: dict[tuple[QuotaOwnerKind, str, QuotaKind, date], int] = {}

    async def get(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date) -> int:
        return self.rows.get((owner_kind, owner_id, kind, start), 0)

    async def add(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date, amount: int) -> int:
        key = (owner_kind, owner_id, kind, start)
        self.rows[key] = self.rows.get(key, 0) + amount
        return self.rows[key]

    async def reset(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date) -> bool:
        return self.rows.pop((owner_kind, owner_id, kind, start), None) is not None

    async def total(self, kind: QuotaKind, start: date) -> int:
        return sum(
            v for (ok, _, k, s), v in self.rows.items() if ok is QuotaOwnerKind.user and k is kind and s == start
        )

    async def top(self, kind: QuotaKind, start: date, owner_kind: QuotaOwnerKind, limit: int) -> Sequence[CounterTotal]:
        found = [
            CounterTotal(ok, oid, v)
            for (ok, oid, k, s), v in self.rows.items()
            if ok is owner_kind and k is kind and s == start
        ]
        return tuple(sorted(found, key=lambda item: -item.used)[:limit])

    async def prune(self, before: date) -> int:
        old = [key for key in self.rows if key[3] < before]
        for key in old:
            del self.rows[key]
        return len(old)


class InMemoryFootprint:
    def __init__(self) -> None:
        self.owners: dict[UUID, ProjectOwner] = {}
        self.storage: dict[tuple[QuotaOwnerKind, str], int] = {}
        self.members: dict[UUID, int] = {}

    async def project_owner(self, project_id: UUID) -> ProjectOwner | None:
        return self.owners.get(project_id)

    async def storage_bytes(self, owner_kind: QuotaOwnerKind, owner_id: str) -> int:
        return self.storage.get((owner_kind, owner_id), 0)

    async def storage_total(self) -> int:
        return sum(self.storage.values())

    async def member_count(self, project_id: UUID) -> int:
        return self.members.get(project_id, 0)

    async def max_members(self, owner_kind: QuotaOwnerKind, owner_id: str) -> int:
        ids = [
            p.project_id
            for p in self.owners.values()
            if (owner_kind is QuotaOwnerKind.org and p.org_id == owner_id)
            or (owner_kind is QuotaOwnerKind.user and p.user_id == owner_id and p.org_id is None)
        ]
        return max((self.members.get(i, 0) for i in ids), default=0)
