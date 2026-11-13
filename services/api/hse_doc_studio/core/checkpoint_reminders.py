"""Напоминание автору о сроке контрольной точки (docs/design/signing-route.md, 16.7): данные и порт хранилища.

Правила (когда пора, ключ повтора) в `core.checkpoint_deadlines`; проход в `use_cases.submission.checkpoint_reminders`.
Состояние подписания точки в напоминании (`CheckpointSigning`) читает `use_cases.signing_route.checkpoint_signing`.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
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


class SigningState(StrEnum):
    """Строка «Подписание» в напоминании о сроке точки (16.7): маршрут идёт, завершён или не отправлен."""

    waiting = "waiting"  # идёт: ждём тех, чья очередь
    completed = "completed"  # все согласовали и подписали
    not_sent = "not_sent"  # черновик, остановлен, возвращён или отменён: на подписи сейчас ничего нет


# Кого ждём, по персоне шага: ru в родительном падеже («ждём научного руководителя»), en с артиклем. Персоны
# соавторов команды (slug автора) называются «автора».
_PERSONA_WHOM: Mapping[str, tuple[str, str]] = {
    "supervisor": ("научного руководителя", "the supervisor"),
    "co_supervisor": ("соруководителя", "the co-supervisor"),
    "academic_supervisor": ("академического руководителя", "the academic supervisor"),
}
_AUTHOR_WHOM = ("автора", "the author")


@dataclass(frozen=True)
class AwaitedSigner:
    """Участник, чья сейчас очередь (или чьё приглашение не принято): персона шага и имя аккаунта, если есть."""

    persona: str
    name: str | None = None

    def whom(self, locale: str | None) -> str:
        """«научного руководителя (Иванов И. И.)», «the supervisor (Ivan Ivanov)»; без имени только роль."""
        ru, en = _PERSONA_WHOM.get(self.persona, _AUTHOR_WHOM)
        role = en if locale == "en" else ru
        return f"{role} ({self.name})" if self.name else role


@dataclass(frozen=True)
class CheckpointSigning:
    """Состояние подписания точки для напоминания: по расчёту маршрута на текущих фактах."""

    state: SigningState
    awaited: tuple[AwaitedSigner, ...] = ()

    def whom(self, locale: str | None) -> str | None:
        """Кого ждём, на языке получателя; None вне идущего маршрута или если ждать некого."""
        if self.state is not SigningState.waiting or not self.awaited:
            return None
        return ", ".join(dict.fromkeys(signer.whom(locale) for signer in self.awaited))


class ICheckpointSigning(Protocol):
    """Состояние подписания точки для напоминания о сроке (16.7). Только читает."""

    async def signing(self, project_id: UUID, profile_id: str) -> CheckpointSigning | None:
        """None, если у точки нет маршрута (снятые с контроля не считаются)."""
        ...
