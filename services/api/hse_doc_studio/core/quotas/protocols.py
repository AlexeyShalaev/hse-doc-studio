from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from hse_doc_studio.core.jobs.quotas import QuotaOwnerKind
from hse_doc_studio.core.quotas.kinds import QuotaKind
from hse_doc_studio.core.quotas.policy import Assessment


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


@dataclass(frozen=True)
class Admission:
    """Итог допуска: `deprioritize` ставит сборку в конец очереди, `warning` несёт превышение."""

    deprioritize: bool = False
    warning: Assessment | None = None


class IQuotaGate(Protocol):
    """Допуск по квотам для мест, где расход возникает: очередь, запись файлов, участники, ИИ-шлюз."""

    async def admit(self, kind: QuotaKind, user_id: UUID | None, org_id: UUID | None, amount: int = 1) -> Admission:
        """Пропускает расход или бросает `QuotaExceededError` по политике установки."""
        ...

    async def charge(self, kind: QuotaKind, user_id: UUID | None, org_id: UUID | None, amount: int = 1) -> None: ...

    async def check_storage_write(self, project_id: UUID, delta_bytes: int) -> None: ...

    async def ensure_member_slot(
        self, project_id: UUID, principal_kind: str | None = None, principal_id: str | None = None
    ) -> None:
        """Место для нового участника; уже состоящий в проекте слот не занимает."""
        ...


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

    async def has_member(self, project_id: UUID, principal_kind: str, principal_id: str) -> bool: ...

    async def max_members(self, owner_kind: QuotaOwnerKind, owner_id: str) -> int:
        """Наибольшее число участников среди живых проектов владельца."""
        ...

    async def storage_total(self) -> int: ...
