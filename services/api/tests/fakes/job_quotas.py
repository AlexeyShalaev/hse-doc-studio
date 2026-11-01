"""Память вместо таблицы quotas и чтения организации проекта."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from hse_doc_studio.core.jobs.quotas import QuotaOverride, QuotaOwnerKind, QuotaResource


class InMemoryQuotaOverrides:
    def __init__(self, *items: QuotaOverride) -> None:
        self._items = {(i.owner_kind, i.owner_id, i.resource): i for i in items}

    async def list_all(self) -> Sequence[QuotaOverride]:
        return tuple(self._items.values())

    async def set(self, override: QuotaOverride) -> None:
        self._items[(override.owner_kind, override.owner_id, override.resource)] = override

    async def delete(self, owner_kind: QuotaOwnerKind, owner_id: str, resource: QuotaResource) -> None:
        self._items.pop((owner_kind, owner_id, resource), None)


class FixedProjectOrgs:
    def __init__(self, org: UUID | None) -> None:
        self._org = org

    async def org_of(self, project_id: UUID) -> UUID | None:
        return self._org
