from __future__ import annotations

from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.git_sync.entities import SyncHealth, SyncState
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.use_cases.git_sync.health import with_failure, with_success

pytestmark = pytest.mark.unit

_AT = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
_STATE = SyncState(local_branch="master", remote_branch="main")


def test__with_failure__network_error__records_health_and_error() -> None:
    state = with_failure(_STATE, GitSyncError(GitErrorCode.offline, "no network"), at=_AT)

    assert state.health is SyncHealth.offline
    assert state.last_error is not None
    assert (state.last_error.code, state.last_error.detail, state.last_error.at) == (
        GitErrorCode.offline,
        "no network",
        _AT,
    )
    assert state.last_fetch_at is None


def test__with_failure__fetch_flag__moves_the_fetch_clock() -> None:
    state = with_failure(_STATE, GitSyncError(GitErrorCode.offline), at=_AT, fetch=True)

    assert state.last_fetch_at == _AT
    assert state.last_fetch_ok_at is None


@pytest.mark.parametrize(
    "code",
    [GitErrorCode.sync_busy_build, GitErrorCode.large_file, GitErrorCode.remote_moved, GitErrorCode.off_branch],
)
def test__with_failure__problem_of_the_project_itself__leaves_the_connection_healthy(code: GitErrorCode) -> None:
    assert with_failure(_STATE, GitSyncError(code), at=_AT) == _STATE


def test__with_success__clears_the_error_and_stamps_the_fetch() -> None:
    broken = with_failure(_STATE, GitSyncError(GitErrorCode.auth_failed), at=_AT)

    healed = with_success(broken, at=_AT)

    assert (healed.health, healed.last_error) == (SyncHealth.ok, None)
    assert healed.last_fetch_ok_at == _AT
