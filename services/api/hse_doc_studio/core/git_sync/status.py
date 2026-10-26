"""Состояние синхронизации, которое видит человек: чистые функции без ввода-вывода."""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.git_sync.entities import SyncBlockReason, SyncHealth, SyncRelation, SyncUiState

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
