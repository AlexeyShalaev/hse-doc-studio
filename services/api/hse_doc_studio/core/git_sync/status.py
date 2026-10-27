"""Состояние синхронизации, которое видит человек: чистые функции без ввода-вывода."""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass

from hse_doc_studio.core.git_sync.entities import (
    CommitBrief,
    SyncBlockReason,
    SyncHealth,
    SyncRelation,
    SyncUiState,
)

_RELATION_STATE = {
    SyncRelation.none: SyncUiState.unfetched,
    SyncRelation.unfetched: SyncUiState.unfetched,
    SyncRelation.remote_empty: SyncUiState.ahead,
    SyncRelation.ahead: SyncUiState.ahead,
    SyncRelation.behind: SyncUiState.behind,
    SyncRelation.diverged: SyncUiState.diverged,
    SyncRelation.in_sync: SyncUiState.up_to_date,
}


_HEALTH_STATE = {
    SyncHealth.unauthenticated: SyncUiState.auth_failed,
    SyncHealth.offline: SyncUiState.offline,
}


@dataclass(frozen=True)
class StatusInputs:
    connected: bool
    relation: SyncRelation
    health: SyncHealth = SyncHealth.ok
    has_operation: bool = False
    has_pending: bool = False
    blocked: SyncBlockReason | None = None


def derive_relation(*, ahead: int, behind: int, tracking_exists: bool, remote_empty: bool = False) -> SyncRelation:
    """Соотношение веток по числу коммитов; remote_empty — удалённый репозиторий пуст (первый push)."""
    if remote_empty:
        return SyncRelation.remote_empty
    if not tracking_exists:
        return SyncRelation.unfetched
    if ahead and behind:
        return SyncRelation.diverged
    if ahead:
        return SyncRelation.ahead
    if behind:
        return SyncRelation.behind
    return SyncRelation.in_sync


def derive_ui_state(inputs: StatusInputs) -> SyncUiState:
    """Состояние по приоритету: нет remote, операция, конфликты, блокировка, здоровье, затем отношение веток."""
    if not inputs.connected:
        return SyncUiState.no_remote
    forced = (
        (inputs.has_operation, SyncUiState.syncing),
        (inputs.has_pending, SyncUiState.conflicts),
        (inputs.blocked is not None, SyncUiState.blocked),
    )
    for active, state in forced:
        if active:
            return state
    if inputs.health != SyncHealth.ok:
        return _HEALTH_STATE.get(inputs.health, SyncUiState.error)
    return _RELATION_STATE[inputs.relation]


@dataclass(frozen=True)
class RefComparison:
    """Что дороже всего в статусе: сравнение двух веток. Зависит только от коммитов на их концах."""

    ahead: int
    behind: int
    behind_files: int
    incoming: tuple[CommitBrief, ...]
    outgoing: tuple[CommitBrief, ...]
    # Коммиты со служебной подписью, которые ещё не отправлены.
    unpublished_bot_commits: int


# Ключ: папка проекта, конец локальной ветки, конец отслеживаемой, удалённый репозиторий пуст.
MemoKey = tuple[str, str | None, str | None, bool]


class RefStatusMemo:
    """Запоминает сравнение веток по их концам: опрос статуса раз в секунду не гоняет git по истории.

    Ключ меняется с каждым новым коммитом на любом конце, поэтому устаревшего ответа быть не может.
    """

    def __init__(self, capacity: int = 64) -> None:
        self._capacity = capacity
        self._items: OrderedDict[MemoKey, RefComparison] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: MemoKey) -> RefComparison | None:
        with self._lock:
            value = self._items.get(key)
            if value is not None:
                self._items.move_to_end(key)
            return value

    def put(self, key: MemoKey, value: RefComparison) -> None:
        with self._lock:
            self._items[key] = value
            self._items.move_to_end(key)
            while len(self._items) > self._capacity:
                self._items.popitem(last=False)
