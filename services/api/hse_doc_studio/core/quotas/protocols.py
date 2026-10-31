from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.quotas import QuotaOwnerKind
from hse_doc_studio.core.quotas.kinds import QuotaKind


@dataclass(frozen=True)
class ProjectOwner:
    """Кому принадлежит проект: человеку или организации (ровно одно из двух)."""

    project_id: UUID
    user_id: str | None
    org_id: str | None


@dataclass(frozen=True)
class CounterTotal:
    owner_kind: QuotaOwnerKind
    owner_id: str
    used: int


class IUsageCounters(Protocol):
    """Счётчики расхода за период (сборки, токены ИИ)."""

    async def get(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date) -> int: ...

    async def add(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date, amount: int) -> int:
        """Атомарно прибавляет и возвращает новое значение."""
        ...

    async def reset(self, owner_kind: QuotaOwnerKind, owner_id: str, kind: QuotaKind, start: date) -> bool:
        """Обнуляет период владельца; `False`, если строки не было."""
        ...

    async def total(self, kind: QuotaKind, start: date) -> int: ...

    async def top(
        self, kind: QuotaKind, start: date, owner_kind: QuotaOwnerKind, limit: int
    ) -> Sequence[CounterTotal]: ...

    async def prune(self, before: date) -> int:
        """Стирает строки с началом периода раньше `before`; возвращает число стёртых."""
        ...


class IOwnerFootprint(Protocol):
    """Расход, который считается по таблицам проектов, а не счётчиком."""

    async def project_owner(self, project_id: UUID) -> ProjectOwner | None:
        """`None`, если проекта нет или он удалён."""
        ...

    async def storage_bytes(self, owner_kind: QuotaOwnerKind, owner_id: str) -> int:
        """Сумма измерений мест живых проектов владельца."""
        ...

    async def member_count(self, project_id: UUID) -> int: ...

    async def max_members(self, owner_kind: QuotaOwnerKind, owner_id: str) -> int:
        """Наибольшее число участников среди живых проектов владельца."""
        ...

    async def storage_total(self) -> int: ...
