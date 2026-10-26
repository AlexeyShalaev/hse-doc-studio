"""Как сбой обращения к удалённому репозиторию отражается на здоровье подключения проекта."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from hse_doc_studio.core.git_sync.entities import LastError, SyncHealth, SyncState
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.fetch_schedule import health_for

# Коды, которые говорят о состоянии проекта или этой Студии, а не об удалённом репозитории.
_LOCAL_CODES = frozenset(
    {
        GitErrorCode.sync_busy,
        GitErrorCode.sync_busy_build,
        GitErrorCode.sync_incomplete,
        GitErrorCode.off_branch,
        GitErrorCode.profile_required,
        GitErrorCode.store_untrusted,
        GitErrorCode.remote_schema_newer,
        GitErrorCode.unrelated_histories,
        GitErrorCode.not_a_studio_project,
        GitErrorCode.large_file,
        GitErrorCode.secrets_unavailable,
        GitErrorCode.remote_moved,
    }
)


def with_failure(state: SyncState, exc: GitSyncError, *, at: datetime, fetch: bool = False) -> SyncState:
    """Состояние после сбоя: сетевые коды портят здоровье, коды о самом проекте его не трогают.

    `fetch`: сбой случился при выборке, и фоновая выборка отсчитывает срок от этого момента.
    """
    if exc.code in _LOCAL_CODES:
        return state
    failed = replace(state, health=health_for(exc.code), last_error=LastError(exc.code, exc.detail, at))
    return replace(failed, last_fetch_at=at) if fetch else failed


def with_success(state: SyncState, *, at: datetime) -> SyncState:
    return replace(state, health=SyncHealth.ok, last_fetch_at=at, last_fetch_ok_at=at, last_error=None)
