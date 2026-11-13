"""Напоминание автору о сроке контрольной точки (docs/design/signing-route.md, 16.7): данные и порт хранилища.

Правила (когда пора, ключ повтора) в `core.checkpoint_deadlines`; проход в `use_cases.submission.checkpoint_reminders`.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class DueCheckpoint:
    """Срок точки из копии в каталоге проектов (`projects.deadlines`), который скоро наступит."""

    project_id: UUID
    project_name: str
    profile_id: str
    deadline: datetime
    # Название точки `{ru, en}` из версии шаблона проекта.
    name: Mapping[str, str] = field(default_factory=dict)

    def label(self, locale: str | None) -> str:
        """Название точки на языке получателя, иначе по-русски, иначе id точки."""
        return self.name.get(locale or "") or self.name.get("ru") or next(iter(self.name.values()), self.profile_id)


@dataclass(frozen=True)
class ReminderRecipient:
    """Кому напомнить: владелец-человек проекта или участник с персоной автора (`users.id`, язык аккаунта)."""

    user_id: str
    locale: str | None = None


class ICheckpointReminderStore(Protocol):
    """Чтение для напоминаний о сроке точки; всё, кроме `due`, идёт в транзакции прохода по одной точке."""

    async def due(self, *, now: datetime, until: datetime) -> list[DueCheckpoint]:
        """Сроки точек живых (не удалённых и не в архиве) проектов в промежутке `(now, until]`."""
        ...

    async def lock(self, key: str) -> None:
        """Блокировка ключа повтора до конца транзакции: одновременные проходы одну точку не напоминают дважды."""
        ...

    async def built(self, project_id: UUID, profile_id: str, *, since: datetime) -> list[datetime]:
        """Моменты сборки пакетов точки не раньше `since` (записи сдачи)."""
        ...

    async def recipients(self, project_id: UUID) -> list[ReminderRecipient]:
        """Владелец-человек проекта и участники с персоной автора; отключённые аккаунты не входят."""
        ...

    async def reminded(self, user_ids: Collection[str], key: str) -> set[str]:
        """Кому из `user_ids` напоминание с ключом повтора `key` уже приходило."""
        ...
